#!/bin/bash
# TypeScript 프로젝트 코드 수정 완료 후 빌드 확인
# Stop hook에서 호출됨

# stdin에서 hook 데이터 읽기
HOOK_DATA=$(cat)

# 프로젝트 디렉토리로 이동
cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0

# package.json이 있는지 확인 (Node.js/TypeScript 프로젝트인지)
if [[ ! -f "./package.json" ]]; then
    exit 0
fi

# TypeScript 설정 파일이 있는지 확인
if [[ ! -f "./tsconfig.json" ]]; then
    exit 0
fi

# git으로 수정된 TypeScript 파일이 있는지 확인
MODIFIED_TS=$(git diff --name-only 2>/dev/null | grep -E '\.tsx?$' || true)
STAGED_TS=$(git diff --cached --name-only 2>/dev/null | grep -E '\.tsx?$' || true)

# TypeScript 파일이 수정되지 않았으면 빌드 스킵
if [[ -z "$MODIFIED_TS" && -z "$STAGED_TS" ]]; then
    exit 0
fi

echo "🔨 TypeScript 파일 변경 감지. 타입 체크 실행 중..."

# package.json에서 build 스크립트 확인
HAS_BUILD_SCRIPT=$(cat package.json | jq -r '.scripts.build // empty' 2>/dev/null)

if [[ -n "$HAS_BUILD_SCRIPT" ]]; then
    # npm run build 사용
    BUILD_OUTPUT=$(npm run build 2>&1)
    BUILD_EXIT_CODE=$?
else
    # tsc --noEmit으로 타입 체크만 수행
    BUILD_OUTPUT=$(npx tsc --noEmit 2>&1)
    BUILD_EXIT_CODE=$?
fi

if [[ $BUILD_EXIT_CODE -eq 0 ]]; then
    echo "✅ TypeScript 빌드 성공!"
    exit 0
else
    echo "❌ TypeScript 빌드 실패!"
    echo ""
    echo "$BUILD_OUTPUT" | tail -50
    # exit code 2: Claude에게 오류 피드백 전달
    exit 2
fi
