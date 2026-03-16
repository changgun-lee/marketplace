#!/bin/bash
# TypeScript 프로젝트 코드 수정 완료 후 빌드 확인
# Stop hook에서 호출됨

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

# TypeScript 프로젝트 디렉토리 목록 수집 (package.json + tsconfig.json 모두 있는 경우)
PROJECT_DIRS=()

# 현재 디렉토리에 TypeScript 프로젝트가 있는 경우
if [[ -f "./package.json" && -f "./tsconfig.json" ]]; then
    PROJECT_DIRS+=(".")
fi

# 바로 하위 디렉토리에 TypeScript 프로젝트가 있는 경우
for dir in */; do
    if [[ -f "${dir}package.json" && -f "${dir}tsconfig.json" ]]; then
        PROJECT_DIRS+=("${dir%/}")
    fi
done

# TypeScript 프로젝트가 없으면 종료
if [[ ${#PROJECT_DIRS[@]} -eq 0 ]]; then
    exit 0
fi

# git으로 수정된 TypeScript 파일이 있는지 확인
MODIFIED_TS=$(git diff --name-only 2>/dev/null | grep -E '\.tsx?$' || true)
STAGED_TS=$(git diff --cached --name-only 2>/dev/null | grep -E '\.tsx?$' || true)

# TypeScript 파일이 수정되지 않았으면 빌드 스킵
if [[ -z "$MODIFIED_TS" && -z "$STAGED_TS" ]]; then
    exit 0
fi

# 전체 빌드 결과 추적
OVERALL_EXIT_CODE=0
FAILED_PROJECTS=()

# 각 프로젝트 디렉토리에서 빌드 실행
BUILD_ERRORS=""
for PROJECT_DIR in "${PROJECT_DIRS[@]}"; do
    echo "🔨 TypeScript 파일 변경 감지. 타입 체크 실행 중... (${PROJECT_DIR})" >&2

    # package.json에서 build 스크립트 확인
    HAS_BUILD_SCRIPT=$(cat "${PROJECT_DIR}/package.json" | jq -r '.scripts.build // empty' 2>/dev/null)

    if [[ -n "$HAS_BUILD_SCRIPT" ]]; then
        # npm run build 사용
        BUILD_OUTPUT=$(cd "$PROJECT_DIR" && npm run build 2>&1)
        BUILD_EXIT_CODE=$?
    else
        # tsc --noEmit으로 타입 체크만 수행
        BUILD_OUTPUT=$(cd "$PROJECT_DIR" && npx tsc --noEmit 2>&1)
        BUILD_EXIT_CODE=$?
    fi

    if [[ $BUILD_EXIT_CODE -eq 0 ]]; then
        echo "✅ TypeScript 빌드 성공! (${PROJECT_DIR})" >&2
    else
        echo "❌ TypeScript 빌드 실패! (${PROJECT_DIR})" >&2
        OVERALL_EXIT_CODE=1
        FAILED_PROJECTS+=("$PROJECT_DIR")
        BUILD_ERRORS="${BUILD_ERRORS}[${PROJECT_DIR}]
$(echo "$BUILD_OUTPUT" | tail -50)

"
    fi
done

if [[ $OVERALL_EXIT_CODE -eq 0 ]]; then
    exit 0
else
    report_block "TypeScript 빌드 실패 프로젝트: ${FAILED_PROJECTS[*]}

${BUILD_ERRORS}"
fi
