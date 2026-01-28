---
name: commit
description: 현재 워크스페이스의 모든 하위 프로젝트에서 변경 사항을 커밋하고 push하는 스킬.
disable-model-invocation: true
allowed-tools: Bash(git:*), Bash(ls:*), Bash(pwd:*), Bash(find:*), Bash(basename:*), AskUserQuestion
---

현재 워크스페이스의 모든 하위 리파지토리에서 변경 사항을 커밋하고 origin으로 push

## 작업 순서

### 1단계: 현재 위치 확인

현재 디렉토리가 워크스페이스 폴더인지 확인합니다. 워크스페이스 폴더는 하위에 여러 git 리파지토리를 포함하는 폴더입니다.

```bash
pwd
ls -la
```

### 2단계: 작업 디렉토리 이름 추출

현재 디렉토리 이름을 커밋 메시지 제목으로 사용합니다:
```bash
basename "$(pwd)"
```

### 3단계: 하위 프로젝트 탐색

현재 디렉토리의 하위 폴더 중 git 리파지토리인 것들을 찾습니다:
```bash
for dir in */; do
  if [ -d "$dir/.git" ] || git -C "$dir" rev-parse --git-dir > /dev/null 2>&1; then
    echo "$dir"
  fi
done
```

### 4단계: 각 프로젝트별 처리

각 하위 프로젝트에 대해 순서대로 다음을 수행합니다:

#### 4.1 변경 사항 확인
```bash
cd 프로젝트폴더
git status --porcelain
```

변경 사항이 없으면 해당 프로젝트는 건너뜁니다.

#### 4.2 변경 사항 스테이징
```bash
git add -A
```

#### 4.3 diff 내용 출력
```bash
git diff --cached
```

#### 4.4 사용자 승인 요청

AskUserQuestion 도구를 사용하여 사용자에게 커밋 승인을 요청합니다:
- 프로젝트 이름과 변경 내용 요약을 보여줌
- "커밋" 또는 "건너뛰기" 선택지 제공

#### 4.5 커밋 (승인된 경우)

커밋 메시지:
- **제목**: 작업 디렉토리 이름 (2단계에서 추출한 값)
- **내용**: 없음

```bash
git commit -m "작업디렉토리이름"
```

#### 4.6 Push
```bash
git push origin HEAD
```

### 5단계: 결과 요약

모든 프로젝트 처리 완료 후:
- 커밋된 프로젝트 목록
- 건너뛴 프로젝트 목록 (변경 없음 또는 사용자 거부)
- push 성공/실패 여부

## 주의사항

- 각 프로젝트마다 개별적으로 사용자 승인을 받습니다
- 사용자가 "건너뛰기"를 선택하면 해당 프로젝트의 스테이징을 취소하고 다음 프로젝트로 넘어갑니다
- push 실패 시 에러 메시지를 출력하고 계속 진행합니다
