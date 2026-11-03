# GPT Java Formatter Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 기존 Java 포맷터를 Codex에서 스킬과 자동 훅으로 사용할 수 있게 배포한다.

**Architecture:** 독립적인 `plugins/gpt-java-formatter`에 기존 Java 엔진과 Eclipse 설정을 포함한다.
Python 실행기가 CLI 파일 인자와 Codex PostToolUse JSON을 받아 동일한 jbang 실행 경로를 사용한다.
기존 Edit/Write 훅과 대응되는 apply_patch의 추가·수정·이동 대상만 자동 처리한다.

**Tech Stack:** Python 3 표준 라이브러리, jbang, 기존 Eclipse JDT, Codex 플러그인 JSON.

**Spec:** 사용자의 gpt-java-formatter 생성 요청 및 “2: 스킬 + 자동 훅 이식” 선택.

## Global Constraints

- 기존 java-formatter와 포맷 규칙을 보존한다. 새 패키지는 단독 설치 가능해야 한다.
- 임시 파일과 테스트 산출물은 이 프로젝트 하위에 둔다.
- 사용자가 지정하거나 실제 패치에 포함된 파일만 대상으로 한다. 전체 저장소를 탐색하지 않는다.
- 파일 경로는 개별 프로세스 인자로 전달한다. Claude 환경변수와 jq에 의존하지 않는다.
- 설치·전역 설정 변경·커밋은 이번 작업에 포함하지 않는다.

## Review Focus

- 공백/셸 특수문자 경로와 여러 파일이 각각 별도 인자로 전달되는가.
- 이동은 도착 경로를 처리하고 삭제·비Java·실패한 도구 호출은 처리하지 않는가.
- jbang 부재, 파일 읽기/쓰기 실패, formatter 실패가 성공으로 보고되지 않는가.
- 패키지를 다른 위치에 복사해도 실행되며 기존 플러그인에 의존하지 않는가.
- 변경된 파일만 알리고 반복 포맷팅 결과가 안정적인가.

## Task 1: 실행기와 자동 훅

- [x] `plugins/gpt-java-formatter/tests/test_formatter.py`에 실제 subprocess 경계 테스트를 작성하고 실패를 확인한다.
- [x] `scripts/format_java.py`에 CLI 파일 검증, 패치 경로 추출, jbang 실행, 변경 감지와 JSON 응답을 구현한다.
- [x] Java 엔진/XML/.tool-versions를 포함한다. Java 엔진의 파일별 실패는 비정상 종료로 전달하되 포맷 알고리즘은 유지한다.
- [x] `.codex-plugin/plugin.json`과 `hooks/hooks.json`을 추가한다.
- [x] 테스트를 실행해 정상 처리, 비대상, 오류, 공백 경로, 이동을 검증한다.

## Task 2: 스킬·배포 문서와 실제 검증

- [x] `skills/gpt-java-formatter/SKILL.md`에 설치 위치 기준 실행, 파일 범위, 변경 후 다시 읽기, 실패 보고를 기술한다.
- [x] 플러그인 README와 루트 README, marketplace 등록을 추가한다.
- [x] JSON/셸 문법/스킬 검증 및 실제 jbang 포맷팅과 재실행 안정성을 검증한다.
- [x] 독립 리뷰 후 발견된 결함을 검증하고 관련 테스트를 재실행한다.

## 검증 기록

- Python 3.6에서 subprocess 기반 단위 테스트 10개 통과.
- 실제 jbang: 공백·특수문자·여러 파일 경로, import/중괄호/주석 처리, 원본 출력 일치,
  반복 실행 안정성, 훅 JSON 응답, Java 파일별 예외의 오류 종료 확인.
- 스킬 validator, 전체 플러그인 JSON, 셸 문법, git diff --check 통과.
- 기존 gpt-review-toolkit 테스트 42개 통과.
- 독립 리뷰에서 동일 파일 update→delete 패치의 중간 경로가 남는 후보를 제시했으나,
  실제 apply_patch는 `multiple operations target`으로 해당 입력을 거절했다.
  현재 런타임의 성공한 패치에서는 재현되지 않아 파서는 변경하지 않았다.
- Codex 전역 설치와 실제 설치된 훅의 자동 호출 검증은 수행하지 않았다. 문서화된 JSON을
  실행기에 직접 전달하는 통합 검증으로 확인했다.
