---
name: add
description: 기존 워크스페이스에 리파지토리를 git worktree로 추가하는 스킬. 작업 이름과 리파지토리 이름을 받아서 ~/github/리파지토리에서 찾아 ~/workspaces/작업이름/ 하위에 worktree를 생성함.
disable-model-invocation: true
model: Haiku
argument-hint: "작업이름" "리파지토리이름"
allowed-tools: Bash(mkdir:*), Bash(ls:*), Bash(cd:*), Bash(git:*), Bash(pwd:*), Bash(test:*)
---

기존 워크스페이스에 리파지토리를 git worktree로 추가

## 인자

$ARGUMENTS 형식: `"작업 이름" "리파지토리 이름"`

예시: `"새로운 기능 개발" "rounz-api"`

## 경로 정보

- **워크스페이스 루트**: `${CLAUDE_WORKSPACE_ROOT:-~/workspaces}`
- **GitHub 프로젝트 루트**: `${CLAUDE_GITHUB_ROOT:-~/github}`
- **브랜치 생성 스크립트**: `${CLAUDE_PLUGIN_ROOT}/scripts/make-working-branch.sh`

## 작업 순서

### 1단계: 인자 파싱 및 경로 설정
- 첫 번째 인자: 작업 이름 (공백 허용)
- 두 번째 인자: 리파지토리 이름
- 경로 변수 설정:
```bash
WORKSPACE_ROOT="${CLAUDE_WORKSPACE_ROOT:-$HOME/workspaces}"
GITHUB_ROOT="${CLAUDE_GITHUB_ROOT:-$HOME/github}"
```

### 2단계: 검증
1. 워크스페이스 폴더가 존재하는지 확인
```bash
test -d "$WORKSPACE_ROOT/작업이름"
```
**주의**: 폴더가 존재하지 않으면 에러를 출력하고 작업을 중단합니다.

2. 리파지토리가 존재하는지 확인
```bash
test -d "$GITHUB_ROOT/리파지토리이름"
```
**주의**: 리파지토리가 존재하지 않으면 에러를 출력하고 작업을 중단합니다.

3. 이미 worktree가 추가되어 있는지 확인
```bash
test -d "$WORKSPACE_ROOT/작업이름/리파지토리이름"
```
**주의**: 이미 존재하면 에러를 출력하고 작업을 중단합니다.

### 3단계: 브랜치 생성
리파지토리에서 브랜치 생성:
```bash
cd "$GITHUB_ROOT/리파지토리이름"
"$CLAUDE_PLUGIN_ROOT"/scripts/make-working-branch.sh "작업이름"
```

이 스크립트는 `feature/작업이름` 형식의 브랜치를 `upstream/production` 기반으로 생성합니다.

### 4단계: Git Worktree 생성
```bash
cd "$GITHUB_ROOT/리파지토리이름"
git checkout production
git worktree add "$WORKSPACE_ROOT/작업이름/리파지토리이름" feature/"작업이름"
```

**주의**: 브랜치 이름에서 공백은 `-`로 변환됨 (예: "새로운 기능" → "feature/새로운-기능")

## 주의사항

- 워크스페이스 폴더가 존재하지 않으면 에러를 내고 즉시 작업을 중단
- 리파지토리가 `$GITHUB_ROOT`에 존재하지 않으면 에러를 내고 즉시 작업을 중단
- 이미 해당 리파지토리의 worktree가 존재하면 에러를 내고 즉시 작업을 중단
- 브랜치 이름에서 공백은 `-`로 변환됨

## 결과

성공 시:
- `$WORKSPACE_ROOT/작업이름/리파지토리이름/` 에 worktree가 생성됨
- worktree는 `feature/작업이름` 브랜치를 체크아웃한 상태
