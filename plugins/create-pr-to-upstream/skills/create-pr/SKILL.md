---
name: create-pr
description: 하위 git 프로젝트들에서 origin 브랜치를 upstream의 동일한 이름 브랜치로 PR 생성 (github-cli 필요. brew install gh)
argument-hint: [reviewers (comma-separated)]
disable-model-invocation: true
---

# 하위 프로젝트 PR 일괄 생성

현재 디렉토리의 하위 git 프로젝트들에서 **origin → upstream** 동일 브랜치로 PR을 생성합니다.

## 사용법

```
/create-pr-to-upstream reviewer1,reviewer2
```

## 인자

- `$ARGUMENTS`: 리뷰어 목록 (쉼표로 구분)

## 실행 절차

1. **하위 프로젝트 탐색**: 현재 디렉토리 바로 아래에서 `.git` 폴더가 있는 디렉토리 찾기

2. **각 프로젝트별로 다음 수행**:
   - `git branch --show-current`로 현재 브랜치 확인
   - `git remote -v`로 origin과 upstream 원격 저장소 확인
   - `git status --short`로 커밋되지 않은 변경사항 확인 (있으면 경고)
   - `git log --oneline -3`으로 최근 커밋 확인

3. **PR 생성 전 확인**:
   - upstream에 동일한 이름의 브랜치가 있는지 확인
   - 없으면 upstream/production (또는 main/master)에서 브랜치 생성 필요

4. **PR 생성** (gh CLI 사용):
   ```bash
   gh pr create \
     --repo <upstream-org>/<repo-name> \
     --head <origin-owner>:<branch-name> \
     --base <branch-name> \
     --title "<현재 작업 디렉토리 이름>" \
     --reviewer <reviewers> \
     --body "$(cat <<'EOF'
   ## Summary
   - <프로젝트별 변경사항 요약>

   ## Test plan
   - [ ] 테스트 항목

   🤖 Generated with [Claude Code](https://claude.com/claude-code)
   EOF
   )"
   ```

5. **결과 출력**: 생성된 PR URL 목록을 테이블 형식으로 출력

## 주의사항

- **upstream에 직접 push 금지**: origin에서 upstream으로 PR을 생성해야 함
- upstream에 이미 동일 브랜치가 push되어 있으면:
  1. upstream 브랜치를 base 브랜치(production/main)로 force reset
  2. 그 후 PR 생성
- origin의 remote URL에서 owner 이름 추출 필요 (예: `changgun-lee`)
- upstream의 remote URL에서 org/repo 이름 추출 필요 (예: `team-commdev/rounz-cms-api`)
- **production을 target으로 PR 금지**: 반드시 동일한 이름의 브랜치로 보내야 함

## 예시 출력

```
| 프로젝트 | PR URL |
|---------|--------|
| rounz-cms-api | https://github.com/team-commdev/rounz-cms-api/pull/184 |
| rounz-cms-worker | https://github.com/team-commdev/rounz-cms-worker/pull/168 |
```
