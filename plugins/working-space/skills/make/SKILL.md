---
name: make
description: GitHub 프로젝트들을 위한 작업 공간과 브랜치를 준비하는 스킬. 작업 제목과 리파지토리 목록을 받아서 워크스페이스 폴더와 git worktree를 생성함. production 브랜치에서 작업 브랜치를 생성.
disable-model-invocation: true
model: Haiku
argument-hint: "작업제목" "repo1, repo2, ..."
allowed-tools: Bash(mkdir:*), Bash(ls:*), Bash(cd:*), Bash(git:*), Bash(pwd:*), Bash(test:*)
---

여러 GitHub 프로젝트를 위한 작업 공간을 한 번에 준비

## 인자

$ARGUMENTS 형식: `"작업 제목" "리파지토리1, 리파지토리2, ..."`

예시: `"새로운 기능 개발" "repository1, repository2"`

## 경로 정보

- **워크스페이스 루트**: `$CLAUDE_WORKSPACE_ROOT` (환경변수 미설정 시 `~/workspaces`)
- **GitHub 프로젝트 루트**: `$CLAUDE_GITHUB_ROOT` (환경변수 미설정 시 `~/github`)
- **브랜치 생성 스크립트**: `${CLAUDE_PLUGIN_ROOT}/scripts/make-working-branch.sh`

## 작업 순서

### 0단계: 경로 변수 설정
```bash
WORKSPACE_ROOT="${CLAUDE_WORKSPACE_ROOT:-~/workspaces}"
GITHUB_ROOT="${CLAUDE_GITHUB_ROOT:-~/github}"
```

### 1단계: 인자 파싱
- 첫 번째 인자: 작업 제목 (공백 허용)
- 두 번째 인자: 쉼표로 구분된 리파지토리 목록

### 2단계: 워크스페이스 폴더 생성
```bash
mkdir -p "$WORKSPACE_ROOT"/"작업제목"
```

**주의**: 이미 폴더가 존재하면 에러를 출력하고 작업을 중단합니다.

### 3단계: 각 리파지토리에서 브랜치 생성
각 리파지토리에 대해:
```bash
cd "$GITHUB_ROOT"/리파지토리명
"$CLAUDE_PLUGIN_ROOT"/scripts/make-working-branch.sh "작업제목"
```

이 스크립트는 `feature/작업제목` 형식의 브랜치를 `upstream/production` 기반으로 생성합니다.

### 4단계: Git Worktree 생성
각 리파지토리에 대해:
```bash
cd "$GITHUB_ROOT"/리파지토리명
git checkout production
git worktree add "$WORKSPACE_ROOT"/"작업제목"/리파지토리명 feature/"작업제목"
```

## 주의사항

- 워크스페이스 폴더가 이미 존재하면 에러를 내고 즉시 작업을 중단
- 리파지토리가 `$GITHUB_ROOT`에 존재하지 않으면 해당 리파지토리는 건너뛰고 경고 메시지 출력
- 브랜치 이름에서 공백은 `-`로 변환됨 (예: "새로운 기능" → "feature/새로운-기능")
- 모든 작업 완료 후 결과 요약을 출력

## 결과

성공 시:
- `$WORKSPACE_ROOT/작업제목/` 폴더가 생성됨
- 각 리파지토리의 worktree가 `$WORKSPACE_ROOT/작업제목/리파지토리명/`에 생성됨
- 각 worktree는 `feature/작업제목` 브랜치를 체크아웃한 상태