---
name: squash
description: 현재 프로젝트 및 하위 git 프로젝트들에서 push되지 않은 커밋들을 squash하여 하나의 커밋으로 합침
argument-hint: "커밋 메시지 제목"
disable-model-invocation: true
allowed-tools: Bash(git:*), Bash(ls:*), Bash(pwd:*), Bash(basename:*), Read, AskUserQuestion
---

# Git Squash - 미push 커밋 합치기

현재 프로젝트 및 바로 하위 git 프로젝트들에서 아직 push되지 않은 커밋들을 찾아 하나의 커밋으로 squash합니다.

## 인자

- `$ARGUMENTS`: squash 후 사용할 커밋 메시지 제목 (필수)

## 실행 절차

### 1단계: 인자 확인

`$ARGUMENTS`가 비어있으면 AskUserQuestion으로 커밋 메시지 제목을 물어봅니다.

### 2단계: 대상 프로젝트 수집

현재 디렉토리가 git 프로젝트인지 확인하고, 바로 하위 디렉토리 중 git 프로젝트인 것도 함께 수집합니다.

```bash
# 현재 디렉토리가 git repo인지 확인
git rev-parse --git-dir 2>/dev/null && echo "CURRENT_IS_GIT=true"

# 하위 디렉토리 중 git repo 찾기
for dir in */; do
  if [ -d "$dir/.git" ] || git -C "$dir" rev-parse --git-dir > /dev/null 2>&1; then
    echo "CHILD_GIT=$dir"
  fi
done
```

### 3단계: 커밋되지 않은 변경사항 처리

각 대상 프로젝트에서 커밋되지 않은 변경사항(unstaged/staged)이 있는지 확인합니다:

```bash
# 변경사항 확인 (staged + unstaged + untracked)
git status --porcelain
```

변경사항이 있는 경우:
1. 모든 변경사항을 staging (`git add -A`)
2. 임시 커밋 메시지로 커밋 (`git commit -m "WIP: uncommitted changes"`)
3. 이후 squash 단계에서 다른 미push 커밋들과 함께 하나로 합쳐집니다

### 4단계: 각 프로젝트별 미push 커밋 확인

각 대상 프로젝트에서 현재 브랜치의 미push 커밋을 확인합니다:

```bash
# 현재 브랜치 확인
git branch --show-current

# upstream 추적 브랜치 확인
git rev-parse --abbrev-ref @{upstream} 2>/dev/null

# 미push 커밋 목록 확인
git log @{upstream}..HEAD --oneline
```

- upstream 추적 브랜치가 없는 경우: `origin/<현재브랜치>`를 기준으로 비교
- `origin/<현재브랜치>`도 없는 경우: 해당 프로젝트는 건너뜀 (경고 출력)
- 미push 커밋이 0개인 프로젝트는 건너뜁니다

### 5단계: 사용자 확인

AskUserQuestion으로 squash 대상을 보여주고 확인을 받습니다:

보여줄 정보:
- 각 프로젝트 이름
- 해당 프로젝트의 미push 커밋 수와 목록
- squash 후 사용할 커밋 메시지

### 6단계: Squash 실행

각 프로젝트에서 다음을 수행합니다:

```bash
# 미push 커밋 수 계산
COMMIT_COUNT=$(git log @{upstream}..HEAD --oneline | wc -l | tr -d ' ')

# soft reset으로 커밋들을 unstage 상태로 되돌림
git reset --soft @{upstream}

# 새 커밋 메시지로 커밋
git commit -m "커밋메시지제목"
```

**중요**: `git reset --soft`를 사용하면 파일 변경 내용은 유지하면서 커밋만 합칩니다.

### 7단계: 결과 요약

모든 프로젝트 처리 후 결과를 출력합니다:

- squash 완료된 프로젝트 목록과 합쳐진 커밋 수
- 건너뛴 프로젝트 목록 (미push 커밋 없음)
- push는 하지 않음 (사용자가 직접 확인 후 push)

## 주의사항

- **push는 자동으로 하지 않습니다**. squash 후 사용자가 직접 확인하고 push해야 합니다.
- 커밋되지 않은 변경사항(unstaged/staged/untracked)이 있는 프로젝트는 먼저 자동으로 커밋한 후 squash합니다.
- main, master, production 브랜치에서는 squash를 실행하지 않습니다. 경고를 출력하고 건너뜁니다.
- `git reset --soft`는 되돌릴 수 있습니다 (`git reflog`로 이전 상태 확인 가능).
