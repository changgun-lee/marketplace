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

# 경로를 어휘적(lexical)으로 정규화: 심볼릭 링크를 따라가지 않고
# `.`, `..`, 중복 슬래시만 텍스트 수준에서 정리한다.
#   - 프로젝트 내부에 외부를 가리키는 심볼릭 링크(예: docs/foo -> ~/other)가 있어도
#     프로젝트 디렉토리 경로 아래로 보이면 내부로 간주(사용자의 디렉토리 구조 기준).
#   - `/project/../../etc` 같은 .. 탈출은 정규화 과정에서 외부로 드러나 여전히 차단됨.
normalize_path() {
    local p="$1"
    local result
    # python normpath 성공 여부는 빈 출력이 아니라 종료 코드로 판정.
    # (실패 시 stderr는 억제하지 않아 verbose 모드에서 폴백 사용을 확인 가능)
    if command -v python3 >/dev/null 2>&1; then
        if result=$(printf '%s' "$p" | python3 -c 'import sys, os; sys.stdout.write(os.path.normpath(sys.stdin.read()))'); then
            printf '%s' "$result"
            return
        fi
    fi
    # 폴백: 순수 bash 어휘 정규화 (glob 비활성화로 안전하게 분해)
    local oldIFS="$IFS" part
    local -a parts=() out=()
    IFS=/
    set -f
    parts=($p)
    set +f
    IFS="$oldIFS"
    for part in "${parts[@]}"; do
        case "$part" in
            ''|.) continue ;;
            ..) [[ ${#out[@]} -gt 0 ]] && unset 'out[${#out[@]}-1]' ;;
            *) out+=("$part") ;;
        esac
    done
    local joined=""
    for part in "${out[@]}"; do
        joined="$joined/$part"
    done
    printf '%s' "${joined:-/}"
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
# 논리(logical) 경로 사용: 심볼릭 링크를 해석하지 않아야 토큰 경로와 동일한 기준으로 비교 가능
PROJECT_DIR_ABS=$(cd "$PROJECT_DIR" 2>/dev/null && pwd -L)
if [[ -z "$PROJECT_DIR_ABS" ]]; then
    # 프로젝트 디렉토리를 결정할 수 없으면 검사 불가 → 통과
    exit 0
fi
PROJECT_DIR_ABS=$(normalize_path "$PROJECT_DIR_ABS")

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
# 1순위: Python shlex로 쉘 인용을 인식해 정확하게 토큰화 (공백 포함 경로 보존).
#        comments=True 로 쉘 주석(#...)을 토큰화 단계에서 제거하여,
#        주석 안에 적힌 /abcd/ 같은 경로 형태가 오탐되지 않도록 함.
#        주석은 줄 단위로 끝나므로 개행이 보존된 원본 COMMAND 를 입력으로 사용.
# 2순위(폴백): python3 미존재 또는 파싱 실패 시 주석 제거 후 따옴표 제거 + 구분자 분리.
# 출력은 토큰당 한 줄.
TOKENS=""
if command -v python3 >/dev/null 2>&1; then
    TOKENS=$(printf '%s' "$COMMAND" | python3 -c '
import sys, shlex
try:
    for tok in shlex.split(sys.stdin.read(), posix=True, comments=True):
        # 토큰 내부의 개행은 공백으로 치환해 줄단위 처리와 호환되도록 함
        sys.stdout.write(tok.replace("\n", " ").replace("\r", " ") + "\n")
except Exception:
    sys.exit(1)
' 2>/dev/null) || TOKENS=""
fi

if [[ -z "$TOKENS" ]]; then
    # 폴백: 줄 단위로 쉘 주석(공백 뒤 # 또는 줄 시작 #)을 제거한 뒤 토큰화.
    TOKENS=$(printf '%s' "$COMMAND" \
        | sed 's/[[:space:]]#.*$//; s/^#.*$//' \
        | tr '\n' ' ' \
        | tr -d "\"'\`" \
        | tr ' \t<>|&;()={}' '\n')
fi

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

    # 어휘적으로 정규화 (심볼릭 링크를 따라가지 않음, 대상이 아직 없어도 동작)
    abs_path=$(normalize_path "$expanded")

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
