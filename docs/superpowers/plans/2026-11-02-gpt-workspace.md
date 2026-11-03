# GPT Workspace Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Codex에서 지정한 기반 브랜치와 작업명으로 현재·하위 Git 프로젝트에 작업 공간을 만든다.

**Architecture:** `gpt-workspace` 플러그인의 `make-workspace` 스킬(표시 이름 `Make Workspace`)이
Python 표준 라이브러리 실행기를 호출한다. 실행기는 전체 대상 사전 검사 후 각 프로젝트의
`.worktrees/feature/<정리한 작업명>`에 브랜치와 워크트리를 만들고 JSON으로 경로를 반환한다.

**Tech Stack:** Python 3.6 이상, Git, Codex 스킬·플러그인 메타데이터.

**Spec:** 사용자의 `gpt-workspace` / `Make Workspace` 생성 요청 및 원격 동명 브랜치 부재 시
upstream을 설정하지 않는 1번 선택.

## Global Constraints

- `feature/`의 구분자만 유지하고 작업명의 `/`와 Git ref 금지 문자·패턴은 `-`로 바꾼다.
- 한글·대소문자 등 유효한 문자는 유지한다. 원격 브랜치를 자동 생성하거나 push하지 않는다.
- origin 동명 브랜치가 있으면 그 브랜치만 추적한다. 없으면 upstream은 비어 있어야 한다.
- 원본 checkout, 변경 파일, stash, origin URL을 유지한다. 강제 덮어쓰기나 자동 삭제를 하지 않는다.
- 기반 브랜치의 로컬·원격 커밋이 다르거나 기존 브랜치·경로와 충돌하면 선택을 요청한다.
- 모든 임시 파일과 테스트 저장소는 이 프로젝트 안에 둔다. 기존 미커밋 변경을 보존한다.
- 이번 작업은 플러그인 제작이다. 실제 프로젝트의 작업 브랜치 생성·설치·커밋·push는 포함하지 않는다.

## Review Focus

- Git의 자동 upstream 상속 설정이 켜져 있어도 기반 브랜치를 추적하지 않는가.
- 삭제된 원격 브랜치의 오래된 ref를 동명 원격 브랜치로 오인하지 않는가.
- `.git` 파일인 프로젝트와 중첩 프로젝트를 찾고 `.worktrees` 재탐색을 피하는가.
- 공백·한글·셸 특수문자·금지 ref 패턴과 심볼릭 링크 경로를 안전하게 처리하는가.
- 여러 프로젝트 중 사전 검사 또는 생성이 실패하면 부분 성공을 전체 성공으로 보고하지 않는가.

## Task 1: 실행기와 Git 통합 테스트

- [x] 기존 Git 명령의 upstream 상속 실패를 독립 fixture에서 확인한다.
- [x] `plugins/gpt-workspace/tests/test_workspace.py`에 실제 로컬 bare origin을 사용하는 테스트를 작성하고 실패를 확인한다.
- [x] `scripts/make_workspace.py`에 탐색, 이름 정리, 사전 검사, 생성, upstream 검증, JSON 결과를 구현한다.
- [x] 원격 부재·존재·삭제, 기반 선택 충돌, 원본 변경 보존, 복수 저장소·`.git` 파일·경로 충돌을 검증한다.

## Task 2: 스킬과 배포 정보

- [x] `.codex-plugin/plugin.json`, `skills/make-workspace/SKILL.md`, `agents/openai.yaml`을 추가한다.
- [x] 스킬에 자연어 트리거, 대상 탐색, 충돌 시 결정 질문, 실제 설치 경로 기준 실행, 새 워크트리에서 후속 작업을 명시한다.
- [x] 플러그인 README와 루트 README, marketplace 항목을 추가한다.
- [x] 실제 스킬 사용을 독립 fixture에서 검증하고 실행기 테스트·메타데이터·JSON·셸 문법·diff를 확인한다.

## 검증 기록

- 일반 `git worktree add -b ... origin/develop`가 잘못 `origin/develop`을 추적하는 기본 동작을 독립 fixture에서 재현했다.
- Python 3.6.15 / Git 2.49.0에서 새 플러그인의 실제 Git 통합 테스트 24개 통과.
- 기존 gpt-review-toolkit 42개, block-outside-modification 29개, gpt-java-formatter 10개 테스트 통과.
- 기존 working-space의 원격 URL 보존·오류 처리 셸 테스트 통과. 임시 경로를 이 프로젝트 안으로 지정했다.
- 스킬 validator, 표시 이름·UI 메타데이터·마켓플레이스 항목 검사, 전체 플러그인 JSON·셸 문법·diff 검사 통과.
- 독립 스킬 사용 검증에서 중첩된 두 프로젝트의 워크트리 생성, 올바른 기반 커밋, upstream 미설정,
  원본 변경 보존, 새 워크트리에만 후속 파일 작성까지 확인했다. 명시한 원격 기반과 동명 upstream도 확인했다.
- 독립 리뷰에서 발견한 좁은 fetch 설정, 브랜치 상위·하위 이름 충돌, 유니코드 LF 프레이밍과
  브랜치·원격·태그 이름의 모호성을 재현하고 회귀 테스트로 수정했다. 최종 리뷰에서 미해결 중요 결함 없음.
- 단일 브랜치 clone에서는 기존 fetch 규칙을 유지하면서 동명 원격 브랜치의 정확한 refspec만 추가한다.
  충돌하는 기존 매핑·제외 규칙은 자동 변경하지 않고 결정을 요청한다.
- Codex 전역 설치나 실제 플러그인 UI 호출은 수행하지 않았다. 플러그인 파일을 읽은 독립 에이전트와
  실행기 직접 호출로 검증했다. 실제 프로젝트에 브랜치를 만들거나 커밋·push하지 않았다.
