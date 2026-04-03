---
name: remove
description: 워크스페이스 디렉토리를 정리하는 스킬. 지정된 디렉토리 바로 하위의 git worktree들을 안전하게 제거한 뒤, 디렉토리 전체를 삭제함. 워크스페이스 정리, 작업 공간 삭제, worktree 제거 시 사용.
disable-model-invocation: true
argument-hint: "삭제할 디렉토리 경로"
allowed-tools: Bash(ls:*), Bash(git:*), Bash(rm:*), Bash(pwd:*), Bash(test:*), Bash(basename:*), Bash(realpath:*), AskUserQuestion
---

워크스페이스 디렉토리의 git worktree들을 정리하고 디렉토리를 삭제

## 인자

$ARGUMENTS 형식: `"삭제할 디렉토리 경로"`

예시: `"/Users/gilchris/workspaces/새로운-기능-개발"`

## 작업 순서

### 1단계: 대상 디렉토리 확인

$ARGUMENTS에서 디렉토리 경로를 추출하고 존재 여부를 확인합니다:
```bash
test -d "대상경로"
```

디렉토리가 존재하지 않으면 에러를 출력하고 즉시 중단합니다.

### 2단계: 하위 worktree 목록 확인

대상 디렉토리의 바로 하위 폴더들을 확인합니다:
```bash
ls -d "대상경로"/*/
```

각 하위 폴더가 git worktree인지 확인합니다. worktree는 `.git` 파일(디렉토리가 아닌 파일)이 존재하는 것으로 판별할 수 있습니다:
```bash
test -f "$dir/.git"  # 파일이면 worktree
```

### 3단계: 사용자에게 삭제 확인 요청

AskUserQuestion 도구를 사용하여 삭제할 내용을 보여주고 확인을 요청합니다:
- 대상 디렉토리 경로
- 발견된 worktree 목록
- "삭제 진행" 또는 "취소" 선택지 제공

사용자가 취소하면 즉시 중단합니다.

### 4단계: worktree 제거

각 worktree에 대해 `git worktree remove`를 실행합니다. worktree의 원본 리파지토리를 찾아서 해당 리파지토리에서 worktree를 제거해야 합니다:

```bash
# worktree의 .git 파일에서 원본 리파지토리 경로 추출
cat "$dir/.git"
# 출력 예시: gitdir: /Users/gilchris/github/repo/.git/worktrees/브랜치명

# 원본 리파지토리에서 worktree 제거
git -C "원본리파지토리경로" worktree remove "worktree경로"
```

`git worktree remove`가 실패하면 (커밋되지 않은 변경사항 등) `--force` 옵션 없이 에러를 출력하고 해당 worktree는 건너뜁니다. 사용자에게 상황을 알려주세요.

### 5단계: 디렉토리 삭제

모든 worktree가 정상 제거된 후, 대상 디렉토리를 삭제합니다:
```bash
rm -rf "대상경로"
```

worktree 제거에 실패한 항목이 있었다면, 디렉토리 삭제를 진행하지 않고 사용자에게 알립니다.

### 6단계: 결과 요약

- 제거된 worktree 목록
- 삭제 실패한 worktree 목록 (있는 경우)
- 디렉토리 삭제 여부

## 주의사항

- worktree에 커밋되지 않은 변경사항이 있으면 `git worktree remove`가 실패합니다. `--force`를 자동으로 사용하지 마세요.
- 반드시 사용자 확인을 받은 후에만 삭제를 진행합니다.
- worktree가 아닌 일반 하위 디렉토리는 worktree 제거 단계에서 건너뜁니다.
