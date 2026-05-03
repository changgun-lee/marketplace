#!/bin/bash
# Bash 명령에서 프로젝트 외부 파일을 수정/삭제하는 작업을 차단하는 PreToolUse hook
#
# 동작 개요:
#   1. Bash 명령에 파일을 수정/삭제할 가능성이 있는 키워드(rm, mv, cp, sed -i, >, tee 등)가 포함되어 있는지 확인.
#   2. 명령에 포함된 절대 경로(/...) 또는 홈 경로(~/...)들을 추출.
#   3. 각 경로가 프로젝트 디렉토리(CLAUDE_PROJECT_DIR) 외부를 가리키면 차단.
#
# 안전한 외부 경로(/dev/null, /dev/stdout 등)는 통과시킴.

# jq 실패 시 exit 2 + 평문으로 폴백하는 헬퍼
report_block() {
    local reason="$1"
    local json_output
    json_output=$(jq -n --arg reason "$reason" '{"decision":"block","reason":$reason}' 2>/dev/null)
    if [[ $? -eq 0 && -n "$json_output" ]]; then
        echo "$json_output"
        exit 0
    else
        echo "$reason" >&2
        exit 2
    fi
}

# 화이트리스트: 프로젝트 외부지만 일반적으로 안전한 경로
is_allowed_outside() {
    local path="$1"
    case "$path" in
        /dev/null|/dev/stdout|/dev/stderr|/dev/tty|/dev/zero|/dev/random|/dev/urandom|/dev/stdin)
            return 0 ;;
        /dev/fd/*)
            return 0 ;;
    esac
    return 1
}

# stdin에서 hook 데이터 읽기
HOOK_DATA=$(cat)

# Bash 도구가 아닌 경우 통과 (matcher로 이미 필터링되지만 방어적으로 확인)
TOOL_NAME=$(echo "$HOOK_DATA" | jq -r '.tool_name // empty' 2>/dev/null)
if [[ "$TOOL_NAME" != "Bash" ]]; then
    exit 0
fi

# 실행할 명령 추출
COMMAND=$(echo "$HOOK_DATA" | jq -r '.tool_input.command // empty' 2>/dev/null)
if [[ -z "$COMMAND" ]]; then
    exit 0
fi

# 프로젝트 디렉토리 결정 (환경변수 → cwd → pwd 순)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-}"
if [[ -z "$PROJECT_DIR" ]]; then
    PROJECT_DIR=$(echo "$HOOK_DATA" | jq -r '.cwd // empty' 2>/dev/null)
fi
if [[ -z "$PROJECT_DIR" ]]; then
    PROJECT_DIR="$(pwd)"
fi
PROJECT_DIR_ABS=$(cd "$PROJECT_DIR" 2>/dev/null && pwd -P)
if [[ -z "$PROJECT_DIR_ABS" ]]; then
    # 프로젝트 디렉토리를 결정할 수 없으면 검사 불가 → 통과
    exit 0
fi

# 개행을 공백으로 치환하여 한 덩어리로 검사
COMMAND_FLAT=$(printf '%s' "$COMMAND" | tr '\n' ' ')

# 파일을 수정/삭제할 가능성이 있는 명령 키워드 + 리다이렉션(>, >>)
# - 일반 수정 명령: rm, rmdir, mv, cp, tee, truncate, chmod, chown, chgrp, touch, mkdir, ln, install, patch, dd, unlink
# - 인플레이스 편집: sed -i / sed --in-place
# - 출력 리다이렉션: >, >>
MODIFY_KEYWORDS='\b(rm|rmdir|mv|cp|tee|truncate|chmod|chown|chgrp|touch|mkdir|ln|install|patch|dd|unlink)\b|\bsed[[:space:]]+(-[a-zA-Z]*i\b|--in-place)|>'

if ! printf '%s' "$COMMAND_FLAT" | grep -qiE "$MODIFY_KEYWORDS"; then
    # 수정성 명령이 전혀 없으면 통과
    exit 0
fi

# 토큰 단위로 절대 경로 추출
# 따옴표/백틱 제거 후 공백 및 일반 쉘 구분자로 분리
TOKENS=$(printf '%s' "$COMMAND_FLAT" \
    | tr -d "\"'\`" \
    | tr ' \t<>|&;()={}' '\n')

OUTSIDE_PATHS=()
while IFS= read -r token; do
    [[ -z "$token" ]] && continue

    # 절대 경로 또는 ~ 시작 경로만 검사 (상대 경로는 프로젝트 내부로 간주)
    # 주의: case 패턴에서 ~는 tilde expansion 되므로 escape 필요
    case "$token" in
        /*|\~|\~/*)
            ;;
        *)
            continue
            ;;
    esac

    # ~ 확장
    expanded="${token/#\~/$HOME}"

    # 화이트리스트 통과
    if is_allowed_outside "$expanded"; then
        continue
    fi

    # 부모 디렉토리만 정규화 (대상 파일이 아직 없을 수 있음)
    parent=$(dirname "$expanded")
    base=$(basename "$expanded")
    if abs_parent=$(cd "$parent" 2>/dev/null && pwd -P); then
        abs_path="$abs_parent/$base"
    else
        abs_path="$expanded"
    fi

    # 프로젝트 내부면 통과
    case "$abs_path" in
        "$PROJECT_DIR_ABS"|"$PROJECT_DIR_ABS"/*)
            continue
            ;;
    esac

    OUTSIDE_PATHS+=("$token")
done <<< "$TOKENS"

if [[ ${#OUTSIDE_PATHS[@]} -gt 0 ]]; then
    # 중복 제거하여 표시
    UNIQUE_PATHS=$(printf '%s\n' "${OUTSIDE_PATHS[@]}" | awk 'NF && !seen[$0]++')
    report_block "프로젝트 디렉토리 외부 파일을 수정/삭제하는 Bash 명령이 감지되어 실행을 차단했습니다.

프로젝트 디렉토리: ${PROJECT_DIR_ABS}

명령:
${COMMAND}

프로젝트 외부 경로:
${UNIQUE_PATHS}

이 명령은 프로젝트 외부의 파일이나 디렉토리를 변경할 수 있습니다.
실행이 꼭 필요한 경우 사용자에게 확인을 받은 뒤 사용자가 직접 실행하도록 안내해주세요."
fi

exit 0
