#!/bin/bash
# TypeScript 파일 수정 후 lint + format 실행
# PostToolUse hook에서 호출됨

# stdin에서 hook 데이터 읽기
HOOK_DATA=$(cat)

# 수정된 파일 경로 확인
FILE_PATH=$(echo "$HOOK_DATA" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null)

# TypeScript 파일이 아니면 종료
if [[ ! "$FILE_PATH" =~ \.(ts|tsx)$ ]]; then
    exit 0
fi

# 프로젝트 디렉토리로 이동
cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0

# package.json이 있는 프로젝트 루트 찾기
PROJECT_ROOT="$CLAUDE_PROJECT_DIR"
FILE_DIR=$(dirname "$FILE_PATH")
CHECK_DIR="$FILE_DIR"
while [[ "$CHECK_DIR" != "/" && "$CHECK_DIR" != "." ]]; do
    if [[ -f "$CHECK_DIR/package.json" ]]; then
        PROJECT_ROOT="$CHECK_DIR"
        break
    fi
    CHECK_DIR=$(dirname "$CHECK_DIR")
done

cd "$PROJECT_ROOT" 2>/dev/null || exit 0

# ESLint가 프로젝트에 있으면 해당 파일만 lint 실행
HAS_ESLINT=$(jq -r '.devDependencies.eslint // .dependencies.eslint // empty' package.json 2>/dev/null)
if [[ -z "$HAS_ESLINT" ]]; then
    # eslint 설정 파일로도 확인
    for rc in eslint.config.js eslint.config.mjs eslint.config.cjs .eslintrc .eslintrc.js .eslintrc.cjs .eslintrc.json .eslintrc.yml .eslintrc.yaml; do
        if [[ -f "$rc" ]]; then
            HAS_ESLINT="config"
            break
        fi
    done
fi
if [[ -n "$HAS_ESLINT" ]]; then
    LINT_OUTPUT=$(npx eslint --fix "$FILE_PATH" 2>&1)
    LINT_EXIT=$?
    if [[ $LINT_EXIT -ne 0 ]]; then
        echo "ESLint 오류:"
        echo "$LINT_OUTPUT" | tail -30
        exit 2
    fi
fi

# Prettier가 프로젝트에 있으면 해당 파일만 format 실행
HAS_PRETTIER=$(jq -r '.devDependencies.prettier // .dependencies.prettier // empty' package.json 2>/dev/null)
if [[ -z "$HAS_PRETTIER" ]]; then
    # prettier 설정 파일로도 확인
    for rc in .prettierrc .prettierrc.json .prettierrc.yml .prettierrc.yaml .prettierrc.js .prettierrc.cjs .prettierrc.mjs prettier.config.js prettier.config.cjs prettier.config.mjs .prettierrc.toml; do
        if [[ -f "$rc" ]]; then
            HAS_PRETTIER="config"
            break
        fi
    done
fi
if [[ -n "$HAS_PRETTIER" ]]; then
    PRETTIER_OUTPUT=$(npx prettier --write "$FILE_PATH" 2>&1)
    PRETTIER_EXIT=$?
    if [[ $PRETTIER_EXIT -ne 0 ]]; then
        echo "Prettier 오류:"
        echo "$PRETTIER_OUTPUT" | tail -30
        exit 2
    fi
fi

exit 0
