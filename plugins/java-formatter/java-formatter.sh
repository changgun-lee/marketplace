#!/bin/bash
# Java 파일용 Eclipse formatter
# PostToolUse hook에서 호출됨
# 공백이 있는 경로도 지원 (newline 또는 단일 경로)

FORMATTER_DIR="$HOME/.claude/utils/java-formatter"
FORMATTER_CONFIG="$FORMATTER_DIR/eclipse-formatter.xml"
FORMATTER_JAVA="$FORMATTER_DIR/EclipseFormatter.java"

# 파일 경로가 없으면 종료
if [[ -z "$CLAUDE_FILE_PATHS" ]]; then
    exit 0
fi

# Java 파일만 필터링 (newline 구분자 지원)
JAVA_FILES=()

# 먼저 newline으로 분리 시도, 없으면 전체를 단일 경로로 처리
if [[ "$CLAUDE_FILE_PATHS" == *$'\n'* ]]; then
    # newline으로 구분된 경우
    while IFS= read -r file; do
        if [[ -n "$file" && "$file" == *.java && -f "$file" ]]; then
            JAVA_FILES+=("$file")
        fi
    done <<< "$CLAUDE_FILE_PATHS"
else
    # 단일 경로이거나 공백으로 구분된 경우
    # 먼저 전체 경로가 .java 파일인지 확인
    if [[ "$CLAUDE_FILE_PATHS" == *.java && -f "$CLAUDE_FILE_PATHS" ]]; then
        JAVA_FILES+=("$CLAUDE_FILE_PATHS")
    else
        # 공백으로 구분된 경우 (경로에 공백이 없는 경우만)
        IFS=' ' read -ra FILES <<< "$CLAUDE_FILE_PATHS"
        for file in "${FILES[@]}"; do
            if [[ "$file" == *.java && -f "$file" ]]; then
                JAVA_FILES+=("$file")
            fi
        done
    fi
fi

# Java 파일이 없으면 종료
if [[ ${#JAVA_FILES[@]} -eq 0 ]]; then
    exit 0
fi

# jbang 설치 확인
if ! command -v jbang &> /dev/null; then
    echo "⚠️ jbang이 설치되어 있지 않습니다. 설치: brew install jbang"
    exit 0
fi

# formatter Java 파일 확인
if [[ ! -f "$FORMATTER_JAVA" ]]; then
    echo "❌ formatter를 찾을 수 없습니다: $FORMATTER_JAVA"
    exit 0
fi

echo "🔧 Eclipse formatter로 Java 파일 포맷팅..."

# jbang으로 formatter 실행 (각 파일을 따옴표로 묶어서 전달)
jbang "$FORMATTER_JAVA" "$FORMATTER_CONFIG" "${JAVA_FILES[@]}" 2>&1

if [[ $? -eq 0 ]]; then
    echo "✅ 포맷팅 완료"
else
    echo "⚠️ 포맷팅 중 오류 발생"
fi

exit 0
