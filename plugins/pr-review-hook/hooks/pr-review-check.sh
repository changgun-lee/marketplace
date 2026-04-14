#!/bin/bash
# 코드 수정 완료 후 pr-review-toolkit:review-pr 스킬 실행을 요청하는 Stop hook

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

# stdin에서 hook 데이터 읽기
HOOK_DATA=$(cat)

# stop_hook_active가 true이면 이미 Stop hook에 의해 계속 진행 중이므로
# 무한 루프를 방지하기 위해 즉시 종료
STOP_HOOK_ACTIVE=$(echo "$HOOK_DATA" | jq -r '.stop_hook_active // false' 2>/dev/null)
if [[ "$STOP_HOOK_ACTIVE" == "true" ]]; then
    exit 0
fi

# 프로젝트 디렉토리로 이동
cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || { echo "WARNING: Cannot cd to CLAUDE_PROJECT_DIR=$CLAUDE_PROJECT_DIR" >&2; exit 0; }

# git 저장소가 아니면 종료
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# git으로 수정된 파일이 있는지 확인
MODIFIED_FILES=$(git diff --name-only 2>/dev/null)
STAGED_FILES=$(git diff --cached --name-only 2>/dev/null)

# 수정된 파일이 없으면 스킵
if [[ -z "$MODIFIED_FILES" && -z "$STAGED_FILES" ]]; then
    exit 0
fi

# 변경된 파일 목록 생성
ALL_CHANGED_FILES=$(echo -e "${MODIFIED_FILES}\n${STAGED_FILES}" | sort -u | grep -v '^$')

# 리뷰 대상 확장자 필터링 (.ts, .tsx, .py, .php, .java, .js, .jsx, .kt, .ps1, .sh)
REVIEW_TARGET_FILES=$(echo "$ALL_CHANGED_FILES" | grep -E '\.(ts|tsx|py|php|java|js|jsx|kt|ps1|sh)$')

# 리뷰 대상 파일이 없으면 스킵
if [[ -z "$REVIEW_TARGET_FILES" ]]; then
    exit 0
fi

FILE_COUNT=$(echo "$REVIEW_TARGET_FILES" | wc -l | tr -d ' ')

report_block "코드 수정이 감지되었습니다 (${FILE_COUNT}개 파일 변경).
/pr-review-toolkit:review-pr 스킬을 사용하여 코드 리뷰를 실행해주세요.

변경된 파일:
${REVIEW_TARGET_FILES}"
