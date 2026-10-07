# block-outside-modification

Bash 명령이 프로젝트 밖의 파일을 수정하거나 삭제하려는지 검사하는
Claude Code `PreToolUse` 훅이다.

## 경로 기준

- 허용 범위는 세션 시작 프로젝트(`CLAUDE_PROJECT_DIR`)와 Git에 등록된 같은
  저장소의 worktree다. Git common directory를 확인하므로 별도 clone이나 단순히
  `cd`로 이동한 외부 디렉토리는 허용 범위에 추가되지 않는다.
- 상대 경로는 훅 입력 JSON의 `cwd`를 기준으로 해석한다. 프로젝트 환경변수가
  없으면 `cwd`, 둘 다 없으면 훅 프로세스의 작업 디렉토리를 사용한다.
- 프로젝트 루트의 논리 경로와 실제 경로, 같은 루트를 가리키는 심볼릭 링크
  표기를 인정한다. 대상 파일이 아직 존재하지 않아도 검사한다.
- 기존 정책대로 **프로젝트 내부 경로로 접근하는 심볼릭 링크는 외부를 가리켜도
  허용**한다. 대상 경로 전체를 `realpath`로 변환하는 정책이 아니다.
- `cd`는 상대 경로 해석 기준만 바꾼다. `&&`로 인해 `cd`가 실행되지 않을 수
  있으면 가능한 작업 경로를 모두 검사한다.

## 명령 분석

Python 3.6 이상이 있으면 표준 라이브러리 기반 분석기를 사용한다. 추가 패키지를
설치할 필요는 없다. Git이 없거나 저장소를 확인하지 못하면 시작 프로젝트만 허용한다.

- `rm`, `rmdir`, `unlink`, `touch`, `mkdir`, `truncate`, `tee`의 수정 대상 검사
- `cp`, `ln`, `install`의 목적지와 `mv`의 원본·목적지를 구분
- `chmod`, `chown`, `chgrp`, `sed -i`, `dd of=...` 대상 검사
- 실행 파일의 절대 경로와 읽기 인자는 수정 대상으로 취급하지 않음
- 공백 없는 `>/path`, `2>/path`, `>>`, `&>`, `>|` 등의 리다이렉션 검사
- 따옴표, 공백 포함 경로, 주석, 줄 이어쓰기, `;`, 개행, `&&`, 일반 파이프 처리
- 차단 메시지에 허용 루트, 현재 작업 경로, 정규화된 외부 수정 대상 표시

Python이 없거나 정적으로 해석하지 못하는 구문이면 기존 Bash 휴리스틱으로
전환한다. 변수·명령 치환·glob, here-document, 서브셸, `||`, 백그라운드 실행,
`eval`, 중첩 쉘, `patch` 등은 이 경로를 사용한다. **이때는 기존 검사의 오탐과
상대 경로 누락, worktree 인식 제한이 남으며, Python 미설치 시 공백 포함 경로도
정확히 처리하지 못한다.** 임의의 프로그램이 내부적으로
쓰는 파일까지 분석하는 샌드박스는 아니다. 명령 문자열은 검사 중 실행하지 않는다.

## 검증

저장소 루트에서 실행한다.

```bash
python3 -B -m unittest discover -s plugins/block-outside-modification/tests -v
claude --plugin-dir ./plugins/block-outside-modification plugin validate ./plugins/block-outside-modification
```

테스트는 임시 Git 저장소, worktree, 별도 clone, 심볼릭 링크를 생성한 뒤 실제 훅에
JSON 입력을 전달하고 출력과 종료 코드를 검사한다. 검사 대상 명령은 실행하지 않는다.

대표 입력(프로젝트가 `/workspace/project`인 경우):

```json
{
    "tool_name": "Bash",
    "cwd": "/workspace/project",
    "tool_input": {"command": "touch ../outside/new.txt"}
}
```

외부 수정은 종료 코드 0과
`hookSpecificOutput.permissionDecision: "deny"`로 차단한다. 허용 시에는 출력 없이
종료 코드 0을 반환한다. 기존 Bash 폴백의 출력 형식은 유지한다.
