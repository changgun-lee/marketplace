# gpt-workspace

Codex에서 **Make Workspace** 스킬로 프로젝트별 브랜치와 워크트리를 생성합니다.
스킬 식별자는 `make-workspace`이며 자연어 요청으로도 사용할 수 있습니다.
Python 3.6 이상과 Git이 필요합니다.

## 설치와 사용

이 저장소 루트에서 마켓플레이스를 등록하고 설치합니다.

```bash
codex plugin marketplace add .
codex plugin add gpt-workspace@gilchris-market
```

Codex에서 다음처럼 요청합니다.

```text
'develop' 브랜치 기반, '로그인 API/개선' 작업
```

표시 이름 **Make Workspace**를 선택하거나 `$make-workspace`를 명시할 수도 있습니다.
스킬의 이름·설명과 표시 이름은 각각 `SKILL.md`와 `agents/openai.yaml`에 정의합니다.
형식은 [OpenAI의 스킬 메타데이터 문서](https://developers.openai.com/plugins/deploy/submission-errors#skill-agent-metadata-errors)를 따릅니다.

## 동작

- 명시한 프로젝트가 없으면 현재 프로젝트와 하위 Git 프로젝트를 탐색합니다.
  `.git`이 파일인 checkout도 지원하고, 기존 `.worktrees`와 심볼릭 링크 폴더는 제외합니다.
- 예시의 결과는 `feature/로그인-API-개선` 브랜치와
  `<각 프로젝트>/.worktrees/feature/로그인-API-개선` 워크트리입니다.
- 별도 언급 없는 기반 브랜치 이름은 원격 `origin` 기준입니다. 예시의 `develop`은
  `origin/develop`을 의미하며, 로컬과 커밋이 달라도 원격을 사용합니다.
  로컬 브랜치는 명시적으로 요청한 경우에만 사용하고, 원격 기반이 없으면 로컬로 대체하지 않습니다.
- `feature/`의 구분자만 남기고 작업명에 포함된 `/`, ASCII 공백, Git ref 금지 문자·패턴을
  `-`로 치환합니다. 유효한 한글과 대소문자는 유지합니다.
- 원격에 동일 이름이 있으면 `origin/feature/로그인-API-개선`만 추적합니다.
  없다면 upstream은 **미설정**이며 자동 push하지 않습니다. 기반 브랜치를 추적하지 않습니다.
  단일 브랜치 clone으로 필요한 fetch 매핑이 없다면 기존 규칙을 유지하며 동명 브랜치의 정확한
  refspec만 추가합니다. 기존 매핑이나 제외 규칙과 충돌하면 사용자 결정을 받습니다.
- 원본 checkout·변경 파일·stash·origin URL은 유지합니다. 워크트리 파일은
  로컬 Git `info/exclude`의 `/.worktrees/`로 제외합니다.
- 기반 브랜치가 없거나 기존 브랜치·경로와 충돌하면 사용자 결정을 받습니다.
  기존 원격 작업 브랜치가 기반과 다른 커밋인 경우도 확인합니다.
- 생성한 경로를 후속 작업의 작업 디렉토리로 사용합니다.

## 실행기 직접 검증

```bash
python3 plugins/gpt-workspace/scripts/make_workspace.py --root "/projects" --base "develop" --task "로그인 API/개선" --dry-run
python3 plugins/gpt-workspace/scripts/make_workspace.py --root "/projects" --project "api" --base "origin/develop" --task "로그인 API/개선"
```

`--root`는 프로젝트 루트 또는 프로젝트들을 포함하는 폴더입니다.
`--project`를 반복하면 지정한 프로젝트만 선택합니다. `--base develop`은 `origin/develop`과 같습니다.
원격을 명시하려면 `origin/develop` 또는 `refs/remotes/origin/develop`, 로컬을 명시하려면
`refs/heads/develop`을 사용합니다. 존재하지 않는 origin이나 기반으로 대체하지 않습니다.
`--dry-run`은 원격을 조회하고 계획을 JSON으로 출력하며 변경하지 않습니다.
실제 실행도 JSON을 출력합니다. 오류가 있으면 비정상 종료하고, 이미 생성된 워크트리를 함께 보고합니다.
자동 삭제하지 않으므로 부분 실패 시 실패한 프로젝트의 브랜치·워크트리를 확인해야 합니다.

```bash
python3 -B -m unittest discover -s plugins/gpt-workspace/tests -v
jq empty plugins/gpt-workspace/.codex-plugin/plugin.json
```

테스트는 이 프로젝트 아래에 로컬 bare origin과 작업 저장소를 만들고 정리합니다.
