#!/usr/bin/env bash
#
# 세션 시작 시 현재 디렉토리와 바로 하위 디렉토리들의 git 브랜치를 알려준다.
#
set -euo pipefail

# 작업 기준 디렉토리 결정 (CLAUDE_PROJECT_DIR 우선, 없으면 현재 디렉토리)
base_dir="${CLAUDE_PROJECT_DIR:-$PWD}"

# 특정 디렉토리가 git 저장소인지 확인하고, 맞으면 현재 브랜치를 출력한다.
# 출력 형식: "<표시이름>\t<브랜치>" (브랜치를 못 구하면 출력하지 않음)
print_branch() {
    local dir="$1"
    local label="$2"

    # .git 이 없으면 git 저장소가 아니므로 건너뛴다.
    if [ ! -e "$dir/.git" ]; then
        return
    fi

    local branch
    if branch=$(git -C "$dir" rev-parse --abbrev-ref HEAD 2>/dev/null); then
        if [ "$branch" = "HEAD" ]; then
            # detached HEAD 상태: 짧은 커밋 해시로 표시
            local short
            short=$(git -C "$dir" rev-parse --short HEAD 2>/dev/null || echo "unknown")
            branch="(detached: ${short})"
        fi
        printf '%s\t%s\n' "$label" "$branch"
    fi
}

lines=""

# 1) 현재(기준) 디렉토리
current=$(print_branch "$base_dir" ".")
if [ -n "$current" ]; then
    lines+="$current"$'\n'
fi

# 2) 바로 하위 디렉토리들 (한 단계만)
for sub in "$base_dir"/*/; do
    [ -d "$sub" ] || continue
    sub="${sub%/}"
    name=$(basename "$sub")
    line=$(print_branch "$sub" "$name")
    if [ -n "$line" ]; then
        lines+="$line"$'\n'
    fi
done

# git 저장소가 하나도 없으면 아무 컨텍스트도 추가하지 않는다.
if [ -z "$lines" ]; then
    exit 0
fi

# 표 형태로 정렬하여 사람이 읽기 좋은 컨텍스트 생성
table=$(printf '%s' "$lines" | column -t -s $'\t')

context="현재 작업 디렉토리와 바로 하위 디렉토리들의 git 브랜치 현황입니다:

${table}"

jq -n --arg ctx "$context" '{
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": $ctx
    }
}'

exit 0
