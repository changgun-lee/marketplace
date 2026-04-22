#!/bin/bash
# Bash 명령에 포함된 위험한 SQL 쿼리(DROP, DELETE)의 실행을 차단하는 PreToolUse hook

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

# 개행을 공백으로 치환해서 heredoc 등 다중 라인 SQL도 한 덩어리로 검사
COMMAND_FLAT=$(printf '%s' "$COMMAND" | tr '\n' ' ')

# DROP <object> 패턴 탐지 (대소문자 무관)
# DROP TABLE, DROP DATABASE, DROP SCHEMA, DROP INDEX, DROP VIEW,
# DROP COLUMN, DROP CONSTRAINT, DROP TRIGGER, DROP FUNCTION,
# DROP PROCEDURE, DROP SEQUENCE, DROP USER, DROP ROLE 등
if printf '%s' "$COMMAND_FLAT" | grep -qiE '\bDROP[[:space:]]+(TABLE|DATABASE|SCHEMA|INDEX|VIEW|COLUMN|CONSTRAINT|TRIGGER|FUNCTION|PROCEDURE|SEQUENCE|USER|ROLE|TABLESPACE|TYPE|MATERIALIZED[[:space:]]+VIEW)\b'; then
    report_block "위험한 SQL 쿼리(DROP)가 감지되어 실행을 차단했습니다.

명령:
${COMMAND}

이 명령은 데이터베이스 객체를 영구적으로 삭제할 수 있습니다.
실행이 꼭 필요한 경우 사용자에게 확인을 받은 뒤 사용자가 직접 실행하도록 안내해주세요."
fi

# DELETE FROM 패턴 탐지 (대소문자 무관)
if printf '%s' "$COMMAND_FLAT" | grep -qiE '\bDELETE[[:space:]]+FROM\b'; then
    report_block "위험한 SQL 쿼리(DELETE)가 감지되어 실행을 차단했습니다.

명령:
${COMMAND}

이 명령은 테이블의 데이터를 삭제할 수 있습니다.
실행이 꼭 필요한 경우 사용자에게 확인을 받은 뒤 사용자가 직접 실행하도록 안내해주세요."
fi

# TRUNCATE 패턴 탐지 (대소문자 무관)
# TRUNCATE TABLE tbl / TRUNCATE ONLY tbl / TRUNCATE tbl 모두 대응:
# TRUNCATE 뒤에 공백과 식별자 시작 문자(영문/언더스코어/따옴표/백틱)가 오는 경우
if printf '%s' "$COMMAND_FLAT" | grep -qiE '\bTRUNCATE[[:space:]]+[A-Za-z_"`]'; then
    report_block "위험한 SQL 쿼리(TRUNCATE)가 감지되어 실행을 차단했습니다.

명령:
${COMMAND}

이 명령은 테이블의 모든 데이터를 즉시 비울 수 있습니다.
실행이 꼭 필요한 경우 사용자에게 확인을 받은 뒤 사용자가 직접 실행하도록 안내해주세요."
fi

# ALTER <object> 패턴 탐지 (대소문자 무관)
# ALTER TABLE, ALTER DATABASE, ALTER SCHEMA, ALTER INDEX, ALTER VIEW,
# ALTER COLUMN, ALTER FUNCTION, ALTER PROCEDURE, ALTER SEQUENCE,
# ALTER USER, ALTER ROLE, ALTER TRIGGER, ALTER TABLESPACE, ALTER TYPE,
# ALTER MATERIALIZED VIEW 등
if printf '%s' "$COMMAND_FLAT" | grep -qiE '\bALTER[[:space:]]+(TABLE|DATABASE|SCHEMA|INDEX|VIEW|COLUMN|CONSTRAINT|TRIGGER|FUNCTION|PROCEDURE|SEQUENCE|USER|ROLE|TABLESPACE|TYPE|MATERIALIZED[[:space:]]+VIEW)\b'; then
    report_block "위험한 SQL 쿼리(ALTER)가 감지되어 실행을 차단했습니다.

명령:
${COMMAND}

이 명령은 데이터베이스 객체의 스키마를 변경할 수 있습니다.
실행이 꼭 필요한 경우 사용자에게 확인을 받은 뒤 사용자가 직접 실행하도록 안내해주세요."
fi

exit 0
