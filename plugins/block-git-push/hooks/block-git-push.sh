#!/bin/bash
# Bash 명령에 포함된 git push와 원격 저장소에 쓰기를 발생시키는 gh 명령의 실행을 차단하는 PreToolUse hook

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

# 개행을 공백으로 치환해서 다중 라인 명령도 한 덩어리로 검사
COMMAND_FLAT=$(printf '%s' "$COMMAND" | tr '\n' ' ')

# git push 탐지
# git과 push 사이에 전역 옵션이 끼어 있는 형태도 대응:
# git push, git -C dir push, git --git-dir=/x push, git -c key=val push, git --no-pager push 등
# (git stash push, git commit -m "push" 같은 명령은 차단하지 않음)
GIT_PUSH_REGEX='\bgit([[:space:]]+((-C|-c|--git-dir|--work-tree|--namespace|--exec-path|--config-env)([[:space:]]+|=)[^[:space:]]+|--[A-Za-z-]+|-[A-Za-z]))*[[:space:]]+push\b'
if printf '%s' "$COMMAND_FLAT" | grep -qE "$GIT_PUSH_REGEX"; then
    report_block "git push 명령이 감지되어 실행을 차단했습니다.

명령:
${COMMAND}

이 명령은 로컬 커밋을 원격 저장소에 반영합니다.
push가 꼭 필요한 경우 사용자에게 확인을 받은 뒤 사용자가 직접 실행하도록 안내해주세요."
fi

# gh repo sync/create/delete/edit 탐지 (원격 저장소 자체에 쓰기)
if printf '%s' "$COMMAND_FLAT" | grep -qE '\bgh[[:space:]]+repo[[:space:]]+(sync|create|delete|edit)\b'; then
    report_block "원격 저장소에 쓰기를 발생시키는 gh repo 명령이 감지되어 실행을 차단했습니다.

명령:
${COMMAND}

이 명령은 원격 저장소를 생성/수정/삭제하거나 브랜치를 push할 수 있습니다.
실행이 꼭 필요한 경우 사용자에게 확인을 받은 뒤 사용자가 직접 실행하도록 안내해주세요."
fi

# gh pr create/merge 탐지 (브랜치 push 또는 원격 브랜치 병합 발생)
if printf '%s' "$COMMAND_FLAT" | grep -qE '\bgh[[:space:]]+pr[[:space:]]+(create|merge)\b'; then
    report_block "원격 저장소에 쓰기를 발생시키는 gh pr 명령이 감지되어 실행을 차단했습니다.

명령:
${COMMAND}

gh pr create는 브랜치를 원격에 push할 수 있고, gh pr merge는 원격 브랜치에 병합 커밋을 만듭니다.
실행이 꼭 필요한 경우 사용자에게 확인을 받은 뒤 사용자가 직접 실행하도록 안내해주세요."
fi

# gh release create/upload/edit/delete 탐지 (원격에 릴리스/태그 쓰기)
if printf '%s' "$COMMAND_FLAT" | grep -qE '\bgh[[:space:]]+release[[:space:]]+(create|upload|edit|delete|delete-asset)\b'; then
    report_block "원격 저장소에 쓰기를 발생시키는 gh release 명령이 감지되어 실행을 차단했습니다.

명령:
${COMMAND}

이 명령은 원격 저장소에 릴리스나 태그를 생성/수정/삭제할 수 있습니다.
실행이 꼭 필요한 경우 사용자에게 확인을 받은 뒤 사용자가 직접 실행하도록 안내해주세요."
fi

# gh api 쓰기 요청 탐지
# - -X/--method 로 POST/PUT/PATCH/DELETE 를 지정한 경우
# - -f/-F/--field/--raw-field/--input 으로 본문을 보내는 경우 (기본 메서드가 POST로 바뀜)
if printf '%s' "$COMMAND_FLAT" | grep -qE '\bgh[[:space:]]+api\b'; then
    Q="['\"]?"
    if printf '%s' "$COMMAND_FLAT" | grep -qiE "(-X|--method)([[:space:]]+|=)${Q}(POST|PUT|PATCH|DELETE)\b" ||
        printf '%s' "$COMMAND_FLAT" | grep -qE '(^|[[:space:]])(-f|-F|--field|--raw-field|--input)([[:space:]]|=)'; then
        report_block "원격에 쓰기를 발생시키는 gh api 명령이 감지되어 실행을 차단했습니다.

명령:
${COMMAND}

이 명령은 GitHub API로 원격 리소스를 생성/수정/삭제할 수 있습니다. (-f/-F 등 본문 지정 시 기본 메서드가 POST입니다)
실행이 꼭 필요한 경우 사용자에게 확인을 받은 뒤 사용자가 직접 실행하도록 안내해주세요."
    fi
fi

exit 0
