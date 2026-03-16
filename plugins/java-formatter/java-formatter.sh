#!/bin/bash
# Java 파일용 Eclipse formatter
# PostToolUse hook에서 호출됨
# 공백이 있는 경로는 newline 구분 또는 단일 경로일 때만 지원

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

FORMATTER_DIR="${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set}"
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
    report_block "jbang이 설치되어 있지 않습니다. 설치: brew install jbang"
fi

# formatter Java 파일 확인
if [[ ! -f "$FORMATTER_JAVA" ]]; then
    report_block "formatter를 찾을 수 없습니다: $FORMATTER_JAVA"
fi

# 수정 전 파일 체크섬 저장 (bash 3 호환을 위해 indexed 배열 사용)
CHECKSUMS_BEFORE=()
for file in "${JAVA_FILES[@]}"; do
    CHECKSUMS_BEFORE+=("$(file_checksum "$file")")
done

# jbang으로 formatter 실행
FORMAT_OUTPUT=$(jbang "$FORMATTER_JAVA" "$FORMATTER_CONFIG" "${JAVA_FILES[@]}" 2>&1)
FORMAT_EXIT=$?

if [[ $FORMAT_EXIT -ne 0 ]]; then
    report_block "Java 포맷팅 오류:
$(echo "$FORMAT_OUTPUT" | tail -30)"
fi

# 변경된 파일 확인
CHANGED_FILES=()
for i in "${!JAVA_FILES[@]}"; do
    CHECKSUM_AFTER=$(file_checksum "${JAVA_FILES[$i]}")
    if [[ "${CHECKSUMS_BEFORE[$i]}" != "$CHECKSUM_AFTER" ]]; then
        CHANGED_FILES+=("${JAVA_FILES[$i]}")
    fi
done

# 파일이 변경되었으면 JSON stdout으로 Claude에게 알림
if [[ ${#CHANGED_FILES[@]} -gt 0 ]]; then
    CHANGED_LIST=$(printf '%s, ' "${CHANGED_FILES[@]}")
    CHANGED_LIST=${CHANGED_LIST%, }
    jq -n --arg files "$CHANGED_LIST" '{
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": ("Java 포맷팅으로 파일이 수정되었습니다. 변경된 파일을 다시 읽어주세요: " + $files)
        }
    }'
fi

exit 0
