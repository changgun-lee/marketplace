---
name: make-workspace
description: Use when a Codex user requests Make Workspace, a new branch and worktree in current or child projects, or work phrased as "'xxx' 브랜치 기반, 'yyy' 작업".
---

# Make Workspace

지정한 기반 브랜치에서 `feature/<작업명>`을 만들고, 각 프로젝트의
`.worktrees/feature/<작업명>`에서 작업한다. 기반 브랜치를 upstream으로 상속하지 않는다.

## 입력과 대상

- 요청에서 기반 브랜치 `xxx`, 작업명 `yyy`, 명시한 프로젝트를 확인한다. 기반이나 작업명이
  없으면 조사한 뒤 질문한다. `main`, `production`, 현재 브랜치 등으로 임의 대체하지 않는다.
- 프로젝트를 지정하지 않으면 현재 프로젝트와 그 하위 Git 프로젝트 전체가 대상이다.
  현재 위치가 프로젝트 내부 폴더이면 `git rev-parse --show-toplevel`로 루트를 찾는다.
  현재 위치가 Git 프로젝트 밖이면 현재 폴더 아래를 탐색한다. 상위의 다른 프로젝트로 넓히지 않는다.
- `.git` 디렉토리와 `.git` 파일을 모두 인식한다. 기존 `.worktrees`와 심볼릭 링크 폴더는
  탐색하지 않는다. 같은 저장소의 checkout이 여러 개면 사용할 checkout을 질문한다.
- 사용자에게 적용되는 원본·새 워크트리의 `AGENTS.md`를 확인한다.

## 실행

이 `SKILL.md`의 **실제 설치 경로**에서 `../../scripts/make_workspace.py`를 찾아
절대 경로로 실행한다. 현재 디렉토리나 Claude 환경변수에서 실행기를 찾지 않는다.
Python 3.6 이상과 Git이 필요하다. 값은 셸 코드가 아닌 개별 인자로 안전하게 전달한다.

```bash
python3 "/실제/플러그인/경로/scripts/make_workspace.py" --root "/프로젝트/탐색루트" --base "xxx" --task "yyy" --dry-run
python3 "/실제/플러그인/경로/scripts/make_workspace.py" --root "/프로젝트/탐색루트" --base "xxx" --task "yyy"
```

특정 프로젝트만 지정했다면 `--project "/프로젝트/탐색루트/api"`처럼 대상을 명시한다.
여러 개면 `--project`를 반복한다. 지정한 프로젝트의 하위 저장소까지 자동 확장하지 않는다.
옵션처럼 시작하는 값은 `--task=-작업`처럼 전달한다.

먼저 `--dry-run`의 JSON에서 대상, 기반 커밋, 브랜치와 경로를 확인한다. 충돌이 없고 생성이
이미 요청된 범위이면 추가 승인 없이 두 번째 명령을 실행한다. dry-run은 원격 조회만 하고
파일·브랜치·추적 ref를 변경하지 않는다. 실행기는 전체 대상을 검사하고 필요한 ref를 fetch한 뒤 생성한다.

## 적용 규칙

| 조건 | 처리 |
| --- | --- |
| 작업명에 ASCII 공백·제어문자·`/`·Git ref 금지 문자 | 각각 `-`로 치환 |
| `..`, `@{`, 처음·끝의 `.`, 끝의 `.lock` | 유효하지 않은 부분을 `-`로 치환 |
| 한글·대소문자 등 유효한 문자 | 원래대로 유지 |
| `origin/feature/<작업명>`이 실제 원격에 존재 | 그 브랜치만 upstream으로 설정 |
| 단일 브랜치 clone 등으로 동명 브랜치의 fetch 매핑이 없음 | 기존 규칙을 유지하고 그 브랜치의 정확한 refspec만 추가 |
| 동일 이름의 원격 브랜치가 없음 | upstream을 비워 둠. 기반·다른 브랜치를 추적하지 않음 |
| `.worktrees`가 ignore되지 않음 | 해당 저장소의 로컬 `info/exclude`에 `/.worktrees/` 추가 |

예: `'develop' 브랜치 기반, '로그인 API/개선' 작업` → 브랜치
`feature/로그인-API-개선`, 경로 `<프로젝트>/.worktrees/feature/로그인-API-개선`.
`feature/` 뒤에는 `/`가 남지 않는다. 빈 작업명은 받지 않는다.

기반이 `xxx`이면 origin에서 조회한 `xxx`와 로컬 `xxx`를 확인한다. 둘 중 하나만 존재하면
그 브랜치를 사용하고, 둘이 같은 커밋이면 원격을 사용한다. 서로 다르면
`refs/heads/xxx`와 `origin/xxx` 중 선택을 질문한다. 명시한 기반은 그대로 사용한다.

원격 존재 여부는 `ls-remote`로 확인하므로, 삭제된 원격의 오래된 로컬 추적 ref는 사용하지 않는다.
일반 `git worktree add -b ... origin/xxx`는 기반을 추적할 수 있으므로 실행기를 사용한다.
실행기는 `--no-track`과 기반 커밋 ID로 생성하고 최종 upstream을 검증한다.

## 충돌과 실패

기존 브랜치(상위·하위 이름 충돌 포함)·경로·워크트리 등록, 기반과 다른 커밋의 동명 원격 작업 브랜치,
동명 원격 브랜치 추적과 충돌하는 fetch 매핑·제외 규칙,
남아 있는 브랜치 추적 설정, origin 부재·접근 실패, 기반 부재가 나오면
현재 상태와 선택지·추천 이유를 설명하고 사용자 결정을 받는다. 임의 재사용·이름 변경·기반 변경을 하지 않는다.
사용자 결정이 필요한 질문은 마지막 응답으로 남기고 즉시 턴을 끝낸다. 답변 전에는 도구 호출이나 작업을 재개하지 않는다.

원본 checkout과 변경 파일·stash·origin URL을 유지한다. 자동 stash·원본 브랜치 전환·reset·강제 덮어쓰기를 하지 않는다.
이 스킬은 push하지 않는다. 추후 사용자가 push를 요청하면 동일 이름을 대상으로
`git push --set-upstream origin "feature/<작업명>"`을 사용한다.

비정상 종료 시 JSON의 `error`, `failed_project`, 이미 생성된 `workspaces`를 확인한다.
생성 도중 실패한 프로젝트는 브랜치만 남을 수도 있으므로 `git worktree list`와 `git branch`로 상태를
확인해 보고한다. 전체 성공으로 보고하거나 자동 삭제·전체 재실행하지 않는다.

## 작업 이어가기

성공한 JSON의 프로젝트별 `worktree`를 이후 도구의 작업 디렉토리로 지정한다.
원본 프로젝트 경로에 수정하지 않는다. 여러 프로젝트의 파일과 명령은 각 워크트리에 대응시킨다.
생성만 요청했다면 결과를 보고하고, 구체적인 후속 작업도 요청했다면 해당 워크트리에서 계속 수행한다.
프로젝트·기반·브랜치·실제 워크트리 경로·upstream(없으면 미설정)을 간단히 보고한다.
