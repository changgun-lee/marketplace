# Claude Code Plugin Marketplace

이 프로젝트는 **Claude Code 플러그인 마켓플레이스**입니다. Claude Code의 기능을 확장하는 다양한 플러그인을 개발하고 배포합니다.

## 프로젝트 구조

```
marketplace/
├── .claude-plugin/
│   └── marketplace.json      # 마켓플레이스 정의 파일
├── plugins/
│   ├── java-formatter/       # Java 코드 포맷터
│   ├── java-build-check/     # Java 빌드 검증 훅
│   ├── typescript-build-check/ # TypeScript 빌드 검증 훅
│   ├── working-space/        # Git 작업 공간 관리
│   ├── create-pr-to-upstream/ # PR 일괄 생성
│   ├── self-reflection/      # 설정 개선 제안
│   ├── guidelines/           # 코딩 가이드라인
│   ├── typescript-lint/      # TypeScript lint & format 훅
│   └── squash/               # Git squash (미push 커밋 합치기)
└── CLAUDE.md
```

## 플러그인 목록

### 1. java-formatter
- **설명**: Eclipse 스타일로 Java 코드 포맷팅
- **타입**: Hook (PostToolUse)
- **트리거**: Edit 또는 Write 도구 사용 후
- **의존성**: jbang (`brew install jbang`)

### 2. java-build-check
- **설명**: Java/Kotlin 프로젝트 빌드 검증
- **타입**: Hook (Stop)
- **동작**: 코드 수정 완료 후 `gradlew build` 실행
- **조건**: `.java` 또는 `.kt` 파일이 수정된 경우에만 실행

### 3. typescript-build-check
- **설명**: TypeScript 프로젝트 빌드 검증
- **타입**: Hook (Stop)
- **동작**: 코드 수정 완료 후 `npm run build` 또는 `tsc --noEmit` 실행
- **조건**: `.ts` 또는 `.tsx` 파일이 수정된 경우에만 실행

### 4. working-space
- **설명**: GitHub 프로젝트 작업 공간 및 브랜치 관리
- **타입**: Skill
- **스킬 목록**:
  - `/working-space:make` - 워크스페이스 폴더와 git worktree 생성
  - `/working-space:add` - 기존 워크스페이스에 리파지토리 추가
  - `/working-space:commit` - 하위 프로젝트들의 변경 사항을 커밋하고 push
- **환경변수**:
  - `CLAUDE_WORKSPACE_ROOT`: 워크스페이스 루트 (기본: `~/workspaces`)
  - `CLAUDE_GITHUB_ROOT`: GitHub 프로젝트 루트 (기본: `~/github`)

### 5. create-pr-to-upstream
- **설명**: 하위 프로젝트들에서 origin → upstream PR 일괄 생성
- **타입**: Skill
- **스킬**: `/create-pr-to-upstream:create-pr [reviewers]`
- **의존성**: GitHub CLI (`brew install gh`)

### 6. self-reflection
- **설명**: 대화 히스토리 분석 및 CLAUDE.md/설정 개선 제안
- **타입**: Skill
- **스킬**: `/self-reflection:reflection`
- **원작자**: Alex McFadyen

### 7. guidelines
- **설명**: 코딩 가이드라인 제공
- **타입**: Skill
- **스킬 목록**:
  - `/guidelines:java` - Java 코딩 가이드라인 (들여쓰기, StringUtils, CollectionUtils, Querydsl 등)
- **특징**: 수동 호출 전용 (`disable-model-invocation: true`)

### 8. typescript-lint
- **설명**: TypeScript 파일 수정 후 ESLint와 Prettier 자동 실행
- **타입**: Hook (PostToolUse)
- **트리거**: Edit 또는 Write 도구로 `.ts`/`.tsx` 파일 수정 후
- **동작**: `npx eslint --fix`, `npx prettier --write` 실행. 파일이 변경되면 JSON stdout으로 Claude에게 알림
- **조건**: package.json에 eslint/prettier 의존성 또는 설정 파일이 있는 경우

### 9. squash
- **설명**: 현재 프로젝트 및 하위 프로젝트들에서 미push 커밋을 squash하여 하나로 합침
- **타입**: Skill
- **스킬**: `/squash:squash "커밋 메시지 제목"`
- **특징**: 수동 호출 전용, main/master/production 브랜치 보호

## 플러그인 개발 가이드

### 플러그인 구조

```
plugin-name/
├── .claude-plugin/
│   └── plugin.json           # 플러그인 메타데이터 (필수)
├── skills/                   # 스킬 정의
│   └── skill-name/
│       └── SKILL.md
├── hooks/                    # 훅 스크립트
│   └── hook-script.sh
├── scripts/                  # 유틸리티 스크립트
└── .mcp.json                 # MCP 서버 설정 (선택)
```

### plugin.json 필수 필드

```json
{
  "name": "plugin-name",
  "description": "플러그인 설명",
  "version": "1.0.0",
  "author": {
    "name": "작성자 이름",
    "email": "email@example.com"
  }
}
```

### 훅 타입

- **PreToolUse**: 도구 실행 전
- **PostToolUse**: 도구 실행 후 (matcher: `Edit|Write` 등)
- **Stop**: Claude 응답 완료 시
- **SessionStart**: 세션 시작 시
- **UserPromptSubmit**: 사용자 프롬프트 제출 시

### 훅 스크립트 종료 코드

- `0`: 성공 (stdout의 JSON이 파싱됨)
- `2`: 블로킹 에러 (stdout은 평문 텍스트로 Claude에게 전달, JSON 무시)
- 기타: 비블로킹 에러 (stderr만 verbose 모드에 표시)

### 훅에서 Claude에게 피드백 전달 (JSON stdout)

`exit 0`으로 종료하면서 stdout에 JSON을 출력하면 Claude가 구조화된 피드백을 받습니다.

```bash
# 파일 변경 알림 예시 (PostToolUse)
jq -n '{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "lint/format으로 파일이 수정되었습니다. 변경된 파일을 다시 읽어주세요."
  }
}'
exit 0
```

```bash
# 블로킹 결정 예시 - Claude에게 문제를 알리고 중단 요청
jq -n '{
  "decision": "block",
  "reason": "ESLint 에러가 있습니다. 수정해주세요."
}'
exit 0
```

**주요 JSON 필드:**

| 필드 | 설명 |
|------|------|
| `decision` | `"block"` 시 Claude에게 reason 표시 |
| `reason` | decision이 block일 때 표시할 메시지 |
| `hookSpecificOutput.additionalContext` | Claude에게 전달할 추가 컨텍스트 |
| `continue` | `false`면 Claude 실행 중단 |
| `stopReason` | continue가 false일 때 사용자에게 표시할 이유 |

### 스킬 SKILL.md 프론트매터

```yaml
---
name: skill-name
description: 스킬 설명 (Claude가 자동으로 사용할 때 참조)
disable-model-invocation: true  # 수동 호출만 허용
model: Haiku                    # 사용할 모델
argument-hint: "인자 힌트"
allowed-tools: Bash(git:*), Read
---
```

## 마켓플레이스 설치

```bash
# 마켓플레이스 추가
/plugin marketplace add gilchris/marketplace

# 플러그인 설치
/plugin install java-formatter@gilchris-market
/plugin install working-space@gilchris-market
```

## 로컬 테스트

```bash
# 단일 플러그인 테스트
claude --plugin-dir ./plugins/java-formatter

# 여러 플러그인 테스트
claude --plugin-dir ./plugins/java-formatter --plugin-dir ./plugins/java-build-check
```

## 환경변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `CLAUDE_PROJECT_DIR` | 프로젝트 디렉토리 | - |
| `CLAUDE_PLUGIN_ROOT` | 플러그인 루트 디렉토리 | - |
| `CLAUDE_FILE_PATHS` | 수정된 파일 경로들 | - |
| `CLAUDE_WORKSPACE_ROOT` | 워크스페이스 루트 | `~/workspaces` |
| `CLAUDE_GITHUB_ROOT` | GitHub 프로젝트 루트 | `~/github` |

## 라이선스

GPLv3
