# 하위 Git 저장소 리뷰 구현 계획

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 현재 폴더가 Git 저장소에 속하지 않으면 바로 하위 1단계의 모든 Git 작업 저장소를 처리한다.

**Architecture:** 저장소 탐색과 저장소별 스냅샷 처리를 분리한다. 기존 저장소별 review.json 형식을 유지하고 Stop 응답에서 여러 리뷰 입력을 함께 전달한다.

**Tech Stack:** Python 3.6+, Git, unittest.

**Spec:** 사용자의 요청과 후속 결정 “1 모두 처리”. 현재 폴더가 Git 내부이면 기존 동작을 유지한다. 비 Git 폴더에서는 바로 하위 저장소 모두를 처리하며 재귀 탐색하지 않는다.

## 제약 및 검토 범위

- 기존 미커밋 수정은 보존하고 임시 파일은 프로젝트 안에 둔다.
- 저장소별 경로, HEAD, 소스코드 변경 판별과 반복 요청 억제를 유지한다.
- 심볼릭 링크 폴더는 따라가지 않으며 worktree는 지원한다.
- 한 저장소의 감지 실패는 알리되 다른 저장소 처리는 계속한다.
- 턴 중 추가·제거된 저장소는 기준 상태 부재/접근 실패로 알린다.

## 작업

- [x] `tests/test_review_hook.py`: 비 Git 부모 아래 복수 저장소의 변경, 깊이 제한, 기존 Git 우선, worktree, 중복 요청, 일부 실패를 실제 훅 입력으로 검사한다. 기존 구현에서 새 테스트 실패를 확인한다.
- [x] `hooks/review_hook.py`: `discover_roots(cwd)` 탐색, `handle_repository(root, session, turn, event)` 처리, `handle(data)` 결과 취합을 구현한다. 비 Git 부모의 세션 상태에는 시작 저장소 목록을 기록한다.
- [x] `README.md`, `skills/review/SKILL.md`: 탐색 범위, 여러 JSON 입력, 저장소별 비교 및 실패 보고를 설명한다.
- [x] `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s plugins/gpt-review-toolkit/tests -v`, shell 문법 검사, JSON 검사, `git diff --check`를 실행한다.

기존 수정과 섞이지 않도록 커밋은 만들지 않는다.

## 검증 결과

- 기존 구현에서 하위 저장소 관련 테스트 6건이 실패하는 것을 확인했다.
- 독립 리뷰에서 탐색 단계의 오류 격리 누락을 발견했다. 시간 초과와 잘못된 Git 메타데이터를 재현한 뒤 폴더별 오류 수집으로 수정했다.
- 최종 unittest 42건 통과, 전체 shell 문법 및 플러그인 JSON 검사와 git diff --check 통과.
- 리뷰 스킬 적용 시뮬레이션에서 복수 저장소별 기준 유지, 네 분야 위임, 감지 실패 보고와 수동 탐색 깊이를 확인했다. 설치된 Codex의 실제 자동 후속 리뷰는 실행하지 않았다.
