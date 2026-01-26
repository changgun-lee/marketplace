#!/bin/bash
# Java 프로젝트 코드 수정 완료 후 gradlew build 실행
# Stop hook에서 호출됨

# stdin에서 hook 데이터 읽기
HOOK_DATA=$(cat)

# 마지막 실행된 도구 확인 (Edit 또는 Write인 경우에만)
STOP_REASON=$(echo "$HOOK_DATA" | jq -r '.stop_hook_reason // empty' 2>/dev/null)

# 프로젝트 디렉토리로 이동
cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0

# gradlew 파일이 있는지 확인 (Java/Gradle 프로젝트인지)
if [[ ! -f "./gradlew" ]]; then
    exit 0
fi

# git으로 수정된 Java 파일이 있는지 확인
MODIFIED_JAVA=$(git diff --name-only 2>/dev/null | grep -E '\.java$|\.kt$' || true)
STAGED_JAVA=$(git diff --cached --name-only 2>/dev/null | grep -E '\.java$|\.kt$' || true)

# Java/Kotlin 파일이 수정되지 않았으면 빌드 스킵
if [[ -z "$MODIFIED_JAVA" && -z "$STAGED_JAVA" ]]; then
    exit 0
fi

echo "🔨 Java/Kotlin 파일 변경 감지. gradlew build 실행 중..."

# gradlew build 실행
BUILD_OUTPUT=$(./gradlew build 2>&1)
BUILD_EXIT_CODE=$?

if [[ $BUILD_EXIT_CODE -eq 0 ]]; then
    echo "✅ Build 성공!"
    exit 0
else
    echo "❌ Build 실패!"
    echo ""
    echo "$BUILD_OUTPUT" | tail -50
    # exit code 2: Claude에게 오류 피드백 전달
    exit 2
fi
