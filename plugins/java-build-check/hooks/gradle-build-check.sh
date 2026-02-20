#!/bin/bash
# Java 프로젝트 코드 수정 완료 후 gradlew build 실행
# Stop hook에서 호출됨

# stdin에서 hook 데이터 읽기
HOOK_DATA=$(cat)

# stop_hook_active가 true이면 이미 Stop hook에 의해 계속 진행 중이므로
# 무한 루프를 방지하기 위해 즉시 종료
STOP_HOOK_ACTIVE=$(echo "$HOOK_DATA" | jq -r '.stop_hook_active // false' 2>/dev/null)
if [[ "$STOP_HOOK_ACTIVE" == "true" ]]; then
    exit 0
fi

# 프로젝트 디렉토리로 이동
cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0

# gradlew가 있는 프로젝트 디렉토리 목록 수집
PROJECT_DIRS=()

# 현재 디렉토리에 gradlew가 있는 경우
if [[ -f "./gradlew" ]]; then
    PROJECT_DIRS+=(".")
fi

# 바로 하위 디렉토리에 gradlew가 있는 경우
for dir in */; do
    if [[ -f "${dir}gradlew" ]]; then
        PROJECT_DIRS+=("${dir%/}")
    fi
done

# gradlew 파일이 없으면 종료
if [[ ${#PROJECT_DIRS[@]} -eq 0 ]]; then
    exit 0
fi

# git으로 수정된 Java 파일이 있는지 확인
MODIFIED_JAVA=$(git diff --name-only 2>/dev/null | grep -E '\.java$|\.kt$' || true)
STAGED_JAVA=$(git diff --cached --name-only 2>/dev/null | grep -E '\.java$|\.kt$' || true)

# Java/Kotlin 파일이 수정되지 않았으면 빌드 스킵
if [[ -z "$MODIFIED_JAVA" && -z "$STAGED_JAVA" ]]; then
    exit 0
fi

# 전체 빌드 결과 추적
OVERALL_EXIT_CODE=0
FAILED_PROJECTS=()

# 각 프로젝트 디렉토리에서 빌드 실행
for PROJECT_DIR in "${PROJECT_DIRS[@]}"; do
    echo "🔨 Java/Kotlin 파일 변경 감지. gradlew build 실행 중... (${PROJECT_DIR})" >&2

    # 해당 디렉토리로 이동하여 빌드 실행
    BUILD_OUTPUT=$(cd "$PROJECT_DIR" && ./gradlew build 2>&1)
    BUILD_EXIT_CODE=$?

    if [[ $BUILD_EXIT_CODE -eq 0 ]]; then
        echo "✅ Build 성공! (${PROJECT_DIR})" >&2
    else
        echo "❌ Build 실패! (${PROJECT_DIR})" >&2
        echo "" >&2
        echo "$BUILD_OUTPUT" | tail -50 >&2
        OVERALL_EXIT_CODE=2
        FAILED_PROJECTS+=("$PROJECT_DIR")
    fi
    echo "" >&2
done

if [[ $OVERALL_EXIT_CODE -eq 0 ]]; then
    exit 0
else
    echo "❌ 실패한 프로젝트: ${FAILED_PROJECTS[*]}" >&2
    # exit code 2: Claude에게 오류 피드백 전달
    exit 2
fi
