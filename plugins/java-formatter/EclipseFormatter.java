///usr/bin/env jbang "$0" "$@" ; exit $?
//DEPS org.eclipse.jdt:org.eclipse.jdt.core:3.38.0
//DEPS org.eclipse.platform:org.eclipse.text:3.14.100
//DEPS org.eclipse.platform:org.eclipse.core.runtime:3.31.100
//DEPS org.eclipse.platform:org.eclipse.equinox.common:3.19.100
//DEPS org.eclipse.platform:org.eclipse.core.jobs:3.15.300
//DEPS org.eclipse.platform:org.eclipse.core.resources:3.20.200
//DEPS org.eclipse.platform:org.eclipse.core.contenttype:3.9.400
//DEPS org.eclipse.platform:org.eclipse.equinox.preferences:3.11.100

import org.eclipse.jdt.core.ToolFactory;
import org.eclipse.jdt.core.dom.*;
import org.eclipse.jdt.core.dom.rewrite.ASTRewrite;
import org.eclipse.jdt.core.formatter.CodeFormatter;
import org.eclipse.jface.text.Document;
import org.eclipse.jface.text.IDocument;
import org.eclipse.text.edits.TextEdit;

import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class EclipseFormatter {
    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("Usage: EclipseFormatter <config.xml> <file1.java> [file2.java ...]");
            System.exit(1);
        }

        String configPath = args[0];
        Map<String, String> options = loadEclipseConfig(configPath);

        CodeFormatter formatter = ToolFactory.createCodeFormatter(options);

        for (int i = 1; i < args.length; i++) {
            String filePath = args[i];
            File file = new File(filePath);
            if (!file.exists() || !filePath.endsWith(".java")) {
                continue;
            }

            try {
                String content = Files.readString(file.toPath());

                // 1단계: import 정리 (fully qualified name -> import + simple name)
                String withImports = organizeImports(content, options);

                // 2단계: 중괄호 추가
                String withBraces = addMissingBraces(withImports, options);

                // 3단계: 포맷팅
                TextEdit edit = formatter.format(
                    CodeFormatter.K_COMPILATION_UNIT | CodeFormatter.F_INCLUDE_COMMENTS,
                    withBraces,
                    0,
                    withBraces.length(),
                    0,
                    System.lineSeparator()
                );

                String formatted = withBraces;
                if (edit != null) {
                    IDocument document = new Document(withBraces);
                    edit.apply(document);
                    formatted = document.get();
                }

                // 후처리: stream(), builder() 등은 이전 줄에 붙임 (builder는 뒤 체이닝 유지)
                formatted = fixMethodChainingStart(formatted);

                if (!content.equals(formatted)) {
                    Files.writeString(file.toPath(), formatted);
                    System.out.println("Formatted: " + filePath);
                }
            } catch (Exception e) {
                System.err.println("Error formatting " + filePath + ": " + e.getMessage());
                e.printStackTrace();
            }
        }
    }

    /**
     * stream(), builder() 등 특정 메서드는 이전 줄에 붙임
     * builder 계열은 뒤의 체이닝 메서드는 새 줄로 유지
     * 예: "list\n    .stream()" -> "list.stream()"
     * 예: "Foo\n    .Builder()\n    .method()" -> "Foo.Builder()\n                .method()"
     */
    private static String fixMethodChainingStart(String source) {
        String result = source;

        // 1. 일반 메서드들: 단순히 이전 줄에 붙임
        String[] simpleMethodsToKeepOnSameLine = {
            "stream", "parallelStream",
            "of", "empty", "singleton"
        };

        for (String method : simpleMethodsToKeepOnSameLine) {
            Pattern pattern = Pattern.compile(
                "(\\S)(\\s*\\n\\s*)(\\." + method + "\\s*\\()",
                Pattern.CASE_INSENSITIVE
            );
            result = pattern.matcher(result).replaceAll("$1$3");
        }

        // 2. builder 계열: 이전 줄에 붙이되, 뒤의 체이닝은 새 줄로 유지
        String[] builderMethods = {"builder", "newBuilder", "toBuilder"};
        String chainIndent = "                "; // 16칸

        for (String method : builderMethods) {
            // Builder() 뒤에 .메서드(가 바로 오는 경우: 줄바꿈 유지하며 이전 줄에 붙임
            Pattern patternWithChain = Pattern.compile(
                "(\\S)(\\s*\\n\\s*)(\\." + method + "\\s*\\(\\))(\\s*\\n\\s*)(\\.[a-zA-Z]+\\()",
                Pattern.CASE_INSENSITIVE
            );
            result = patternWithChain.matcher(result).replaceAll("$1$3\n" + chainIndent + "$5");

            // Builder() 뒤에 체이닝이 없는 경우: 단순히 이전 줄에 붙임
            Pattern patternSimple = Pattern.compile(
                "(\\S)(\\s*\\n\\s*)(\\." + method + "\\s*\\()(?!\\)\\s*\\n\\s*\\.)",
                Pattern.CASE_INSENSITIVE
            );
            result = patternSimple.matcher(result).replaceAll("$1$3");
        }

        // 3. Builder() 뒤에 바로 .메서드(가 붙어있는 경우 (같은 줄에서)
        Pattern builderInlinePattern = Pattern.compile(
            "(Builder\\(\\))(\\.[a-zA-Z]+\\()",
            Pattern.CASE_INSENSITIVE
        );
        result = builderInlinePattern.matcher(result).replaceAll("$1\n" + chainIndent + "$2");

        // 4. new ClassName<...>() 뒤에 바로 .메서드(가 붙어있는 경우
        // 예: new ExcelMaker<DosonSalesRow>().downloadDirectory(
        Pattern newInstancePattern = Pattern.compile(
            "(new\\s+[\\w.]+(?:<[^>]+>)?\\s*\\(\\))(\\.[a-zA-Z]+\\()"
        );
        result = newInstancePattern.matcher(result).replaceAll("$1\n" + chainIndent + "$2");

        return result;
    }

    /**
     * fully qualified name을 import 문으로 변환
     * 예: java.util.regex.Pattern -> import java.util.regex.Pattern; + Pattern
     */
    private static String organizeImports(String source, Map<String, String> options) {
        ASTParser parser = ASTParser.newParser(AST.getJLSLatest());
        parser.setSource(source.toCharArray());
        parser.setKind(ASTParser.K_COMPILATION_UNIT);

        Map<String, String> compilerOptions = new HashMap<>();
        compilerOptions.put("org.eclipse.jdt.core.compiler.source",
            options.getOrDefault("org.eclipse.jdt.core.compiler.source", "17"));
        compilerOptions.put("org.eclipse.jdt.core.compiler.compliance",
            options.getOrDefault("org.eclipse.jdt.core.compiler.compliance", "17"));
        compilerOptions.put("org.eclipse.jdt.core.compiler.codegen.targetPlatform",
            options.getOrDefault("org.eclipse.jdt.core.compiler.codegen.targetPlatform", "17"));
        parser.setCompilerOptions(compilerOptions);

        CompilationUnit cu = (CompilationUnit) parser.createAST(null);

        // 기존 import 수집
        Set<String> existingImports = new HashSet<>();
        for (Object imp : cu.imports()) {
            ImportDeclaration importDecl = (ImportDeclaration) imp;
            existingImports.add(importDecl.getName().getFullyQualifiedName());
        }

        // fully qualified name 수집 (코드 내에서 사용된 것들)
        Map<String, String> fqnToSimpleName = new LinkedHashMap<>();
        Set<String> simpleNamesInUse = new HashSet<>();

        cu.accept(new ASTVisitor() {
            @Override
            public boolean visit(QualifiedName node) {
                // import 문 내부는 건너뜀
                if (isInsideImport(node)) {
                    return false;
                }

                String fqn = node.getFullyQualifiedName();
                // 패키지.클래스 형태인지 확인 (최소 2개 이상의 부분, 마지막이 대문자로 시작)
                if (isFullyQualifiedClassName(fqn)) {
                    String simpleName = node.getName().getIdentifier();
                    // java.lang은 import 불필요
                    if (!fqn.startsWith("java.lang.") && !existingImports.contains(fqn)) {
                        // 같은 simple name이 이미 다른 fqn으로 사용 중이면 충돌 - 건너뜀
                        if (!simpleNamesInUse.contains(simpleName) || fqnToSimpleName.containsKey(fqn)) {
                            fqnToSimpleName.put(fqn, simpleName);
                            simpleNamesInUse.add(simpleName);
                        }
                    }
                }
                return true;
            }

            @Override
            public boolean visit(QualifiedType node) {
                // import 문 내부는 건너뜀
                if (isInsideImport(node)) {
                    return false;
                }

                String fqn = getFullyQualifiedName(node);
                if (fqn != null && isFullyQualifiedClassName(fqn)) {
                    String simpleName = node.getName().getIdentifier();
                    if (!fqn.startsWith("java.lang.") && !existingImports.contains(fqn)) {
                        if (!simpleNamesInUse.contains(simpleName) || fqnToSimpleName.containsKey(fqn)) {
                            fqnToSimpleName.put(fqn, simpleName);
                            simpleNamesInUse.add(simpleName);
                        }
                    }
                }
                return true;
            }

            private boolean isInsideImport(ASTNode node) {
                ASTNode parent = node.getParent();
                while (parent != null) {
                    if (parent instanceof ImportDeclaration) {
                        return true;
                    }
                    parent = parent.getParent();
                }
                return false;
            }

            private String getFullyQualifiedName(QualifiedType type) {
                StringBuilder sb = new StringBuilder();
                Type qualifier = type.getQualifier();
                if (qualifier instanceof SimpleType) {
                    sb.append(((SimpleType) qualifier).getName().getFullyQualifiedName());
                } else if (qualifier instanceof QualifiedType) {
                    String qfn = getFullyQualifiedName((QualifiedType) qualifier);
                    if (qfn != null) {
                        sb.append(qfn);
                    }
                }
                if (sb.length() > 0) {
                    sb.append(".");
                }
                sb.append(type.getName().getIdentifier());
                return sb.toString();
            }
        });

        if (fqnToSimpleName.isEmpty()) {
            return source;
        }

        // 소스 코드에서 fully qualified name을 simple name으로 변경
        String result = source;
        for (Map.Entry<String, String> entry : fqnToSimpleName.entrySet()) {
            String fqn = entry.getKey();
            String simpleName = entry.getValue();
            // 단어 경계를 고려하여 변경 (import 문은 제외)
            result = replaceOutsideImports(result, fqn, simpleName);
        }

        // import 문 추가
        result = addImportStatements(result, fqnToSimpleName.keySet());

        return result;
    }

    /**
     * fully qualified class name인지 확인
     * 예: java.util.List -> true, myVariable.field -> false
     */
    private static boolean isFullyQualifiedClassName(String name) {
        String[] parts = name.split("\\.");
        if (parts.length < 2) {
            return false;
        }
        // 마지막 부분이 대문자로 시작해야 함 (클래스명)
        String lastPart = parts[parts.length - 1];
        if (lastPart.isEmpty() || !Character.isUpperCase(lastPart.charAt(0))) {
            return false;
        }
        // 패키지 부분은 소문자로 시작해야 함
        for (int i = 0; i < parts.length - 1; i++) {
            if (parts[i].isEmpty() || !Character.isLowerCase(parts[i].charAt(0))) {
                return false;
            }
        }
        return true;
    }

    /**
     * import 문 외부에서만 fully qualified name을 simple name으로 변경
     */
    private static String replaceOutsideImports(String source, String fqn, String simpleName) {
        // import 문 영역 찾기
        int importEnd = findImportSectionEnd(source);

        if (importEnd == -1) {
            // import 섹션이 없으면 전체에서 변경
            return source.replace(fqn, simpleName);
        }

        // import 섹션 이후 부분만 변경
        String beforeImports = source.substring(0, importEnd);
        String afterImports = source.substring(importEnd);
        afterImports = afterImports.replace(fqn, simpleName);

        return beforeImports + afterImports;
    }

    /**
     * import 섹션의 끝 위치 찾기
     */
    private static int findImportSectionEnd(String source) {
        Pattern importPattern = Pattern.compile("^import\\s+.*?;\\s*$", Pattern.MULTILINE);
        Matcher matcher = importPattern.matcher(source);
        int lastEnd = -1;
        while (matcher.find()) {
            lastEnd = matcher.end();
        }
        return lastEnd;
    }

    /**
     * import 문 추가
     */
    private static String addImportStatements(String source, Set<String> imports) {
        if (imports.isEmpty()) {
            return source;
        }

        // 마지막 import 문 위치 찾기
        Pattern lastImportPattern = Pattern.compile("^(import\\s+.*?;\\s*)$", Pattern.MULTILINE);
        Matcher matcher = lastImportPattern.matcher(source);
        int insertPosition = -1;
        while (matcher.find()) {
            insertPosition = matcher.end();
        }

        if (insertPosition == -1) {
            // import가 없으면 package 문 다음에 추가
            Pattern packagePattern = Pattern.compile("^package\\s+.*?;\\s*$", Pattern.MULTILINE);
            Matcher pkgMatcher = packagePattern.matcher(source);
            if (pkgMatcher.find()) {
                insertPosition = pkgMatcher.end();
            } else {
                // package도 없으면 맨 앞에 추가
                insertPosition = 0;
            }
        }

        // 정렬된 import 문 생성
        List<String> sortedImports = new ArrayList<>(imports);
        Collections.sort(sortedImports);

        StringBuilder importBlock = new StringBuilder();
        if (insertPosition > 0 && source.charAt(insertPosition - 1) != '\n') {
            importBlock.append("\n");
        }
        for (String imp : sortedImports) {
            importBlock.append("import ").append(imp).append(";\n");
        }

        return source.substring(0, insertPosition) + importBlock + source.substring(insertPosition);
    }

    /**
     * if, for, while, do-while 문에 중괄호가 없으면 추가
     */
    private static String addMissingBraces(String source, Map<String, String> options) {
        ASTParser parser = ASTParser.newParser(AST.getJLSLatest());
        parser.setSource(source.toCharArray());
        parser.setKind(ASTParser.K_COMPILATION_UNIT);

        Map<String, String> compilerOptions = new HashMap<>();
        compilerOptions.put("org.eclipse.jdt.core.compiler.source",
            options.getOrDefault("org.eclipse.jdt.core.compiler.source", "17"));
        compilerOptions.put("org.eclipse.jdt.core.compiler.compliance",
            options.getOrDefault("org.eclipse.jdt.core.compiler.compliance", "17"));
        compilerOptions.put("org.eclipse.jdt.core.compiler.codegen.targetPlatform",
            options.getOrDefault("org.eclipse.jdt.core.compiler.codegen.targetPlatform", "17"));
        parser.setCompilerOptions(compilerOptions);

        CompilationUnit cu = (CompilationUnit) parser.createAST(null);
        cu.recordModifications();

        AST ast = cu.getAST();
        ASTRewrite rewriter = ASTRewrite.create(ast);

        cu.accept(new ASTVisitor() {
            @Override
            public boolean visit(IfStatement node) {
                // then 부분 처리
                Statement thenStmt = node.getThenStatement();
                if (thenStmt != null && !(thenStmt instanceof Block)) {
                    Block block = ast.newBlock();
                    Statement copy = (Statement) ASTNode.copySubtree(ast, thenStmt);
                    block.statements().add(copy);
                    rewriter.replace(thenStmt, block, null);
                }

                // else 부분 처리 (else if는 제외)
                Statement elseStmt = node.getElseStatement();
                if (elseStmt != null && !(elseStmt instanceof Block) && !(elseStmt instanceof IfStatement)) {
                    Block block = ast.newBlock();
                    Statement copy = (Statement) ASTNode.copySubtree(ast, elseStmt);
                    block.statements().add(copy);
                    rewriter.replace(elseStmt, block, null);
                }
                return true;
            }

            @Override
            public boolean visit(ForStatement node) {
                Statement body = node.getBody();
                if (body != null && !(body instanceof Block)) {
                    Block block = ast.newBlock();
                    Statement copy = (Statement) ASTNode.copySubtree(ast, body);
                    block.statements().add(copy);
                    rewriter.replace(body, block, null);
                }
                return true;
            }

            @Override
            public boolean visit(EnhancedForStatement node) {
                Statement body = node.getBody();
                if (body != null && !(body instanceof Block)) {
                    Block block = ast.newBlock();
                    Statement copy = (Statement) ASTNode.copySubtree(ast, body);
                    block.statements().add(copy);
                    rewriter.replace(body, block, null);
                }
                return true;
            }

            @Override
            public boolean visit(WhileStatement node) {
                Statement body = node.getBody();
                if (body != null && !(body instanceof Block)) {
                    Block block = ast.newBlock();
                    Statement copy = (Statement) ASTNode.copySubtree(ast, body);
                    block.statements().add(copy);
                    rewriter.replace(body, block, null);
                }
                return true;
            }

            @Override
            public boolean visit(DoStatement node) {
                Statement body = node.getBody();
                if (body != null && !(body instanceof Block)) {
                    Block block = ast.newBlock();
                    Statement copy = (Statement) ASTNode.copySubtree(ast, body);
                    block.statements().add(copy);
                    rewriter.replace(body, block, null);
                }
                return true;
            }
        });

        try {
            IDocument document = new Document(source);
            TextEdit edits = rewriter.rewriteAST(document, compilerOptions);
            edits.apply(document);
            return document.get();
        } catch (Exception e) {
            System.err.println("Warning: Could not add braces: " + e.getMessage());
            return source;
        }
    }

    private static Map<String, String> loadEclipseConfig(String configPath) throws Exception {
        Map<String, String> options = new HashMap<>();
        File configFile = new File(configPath);

        // 기본 설정
        options.put("org.eclipse.jdt.core.formatter.tabulation.char", "space");
        options.put("org.eclipse.jdt.core.formatter.tabulation.size", "4");
        options.put("org.eclipse.jdt.core.formatter.indentation.size", "4");
        options.put("org.eclipse.jdt.core.compiler.source", "17");
        options.put("org.eclipse.jdt.core.compiler.compliance", "17");
        options.put("org.eclipse.jdt.core.compiler.codegen.targetPlatform", "17");

        if (!configFile.exists()) {
            return options;
        }

        // Eclipse formatter XML 파싱
        String content = Files.readString(configFile.toPath());

        // setting id="..." value="..." 패턴 매칭
        Pattern pattern = Pattern.compile("<setting\\s+id=\"([^\"]+)\"\\s+value=\"([^\"]*)\"\\s*/>");
        Matcher matcher = pattern.matcher(content);

        while (matcher.find()) {
            options.put(matcher.group(1), matcher.group(2));
        }

        return options;
    }
}
