#!/bin/bash
# TypeScript 파일 수정 후 lint + format 실행
# PostToolUse hook에서 호출됨

# jq 실패 시 exit 2 + 평문으로 폴백하는 헬퍼
report_block() {
    local reason="$1"
    local json_output
    json_output=$(jq -n --arg reason "$reason" '{"decision":"block","reason":$reason}' 2>/dev/null)
    if [[ $? -eq 0 && -n "$json_output" ]]; then
        echo "$json_output"
        exit 0
    else
        echo "$reason"
        exit 2
    fi
}

# 체크섬 계산 헬퍼 (md5 → md5sum → shasum 폴백)
file_checksum() {
    md5 -q "$1" 2>/dev/null || md5sum "$1" 2>/dev/null | cut -d' ' -f1 || shasum "$1" 2>/dev/null | cut -d' ' -f1
}

# stdin에서 hook 데이터 읽기
HOOK_DATA=$(cat)

# 수정된 파일 경로 확인
FILE_PATH=$(echo "$HOOK_DATA" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null)

# TypeScript 파일이 아니면 종료
if [[ ! "$FILE_PATH" =~ \.(ts|tsx)$ ]]; then
    exit 0
fi

# 프로젝트 디렉토리로 이동
cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || { echo "WARNING: Cannot cd to CLAUDE_PROJECT_DIR=$CLAUDE_PROJECT_DIR" >&2; exit 0; }

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

cd "$PROJECT_ROOT" 2>/dev/null || { echo "WARNING: Cannot cd to PROJECT_ROOT=$PROJECT_ROOT" >&2; exit 0; }

# 수정 전 파일 체크섬 저장
FILE_CHECKSUM_BEFORE=$(file_checksum "$FILE_PATH")

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
        # --fix가 부분 수정했을 수 있으므로 체크섬 확인 후 파일 변경 정보도 포함
        LINT_CHECKSUM=$(file_checksum "$FILE_PATH")
        LINT_CHANGED=""
        if [[ "$FILE_CHECKSUM_BEFORE" != "$LINT_CHECKSUM" ]]; then
            LINT_CHANGED=" (파일이 부분 수정되었습니다. 변경된 파일을 다시 읽어주세요: $FILE_PATH)"
        fi
        report_block "ESLint 오류:
$(echo "$LINT_OUTPUT" | tail -30)${LINT_CHANGED}"
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
        report_block "Prettier 오류:
$(echo "$PRETTIER_OUTPUT" | tail -30)"
    fi
fi

# 파일이 변경되었으면 JSON stdout으로 Claude에게 알림
FILE_CHECKSUM_AFTER=$(file_checksum "$FILE_PATH")
if [[ "$FILE_CHECKSUM_BEFORE" != "$FILE_CHECKSUM_AFTER" ]]; then
    jq -n --arg file "$FILE_PATH" '{
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": ("lint/format으로 파일이 수정되었습니다. 변경된 파일을 다시 읽어주세요: " + $file)
        }
    }'
fi

exit 0
