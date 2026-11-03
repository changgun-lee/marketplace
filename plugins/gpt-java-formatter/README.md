# gpt-java-formatter

Codex용 Java 포맷팅 스킬과 자동 훅입니다. 기존 `java-formatter` 1.0.8의 Eclipse
설정과 후처리를 포함하며, 기존 플러그인 없이 단독 설치할 수 있습니다.

## 설치

Python 3.6 이상, jbang, Java와 플러그인 훅을 지원하는 Codex 로컬 환경이 필요합니다.
기준 Java 버전은 `.tool-versions`의 Temurin 24.0.2+12입니다.
최초 실행에는 jbang의 Eclipse 의존성 다운로드와 컴파일 시간이 필요합니다.

```bash
brew install jbang
codex plugin marketplace add .
codex plugin add gpt-java-formatter@gilchris-market
```

마켓플레이스 추가 명령은 이 저장소 루트에서 실행합니다. 이미 등록했다면 생략합니다.
Codex의 `gilchris-market` 플러그인 목록에서 설치할 수도 있습니다.
설치 후 **훅 내용을 검토하고 신뢰**해야 자동 실행됩니다. 설치만으로 훅이 신뢰되지는 않습니다.

## 사용

Codex에서 `$gpt-java-formatter`와 포맷팅할 Java 파일을 지정합니다.
스킬과 자동 훅은 같은 Python 실행기로 같은 포맷터를 호출합니다.
수동 실행도 가능합니다.

```bash
python3 plugins/gpt-java-formatter/scripts/format_java.py -- "src/One.java" "공백 폴더/Two.java"
```

`CLAUDE_PLUGIN_ROOT`, `CLAUDE_FILE_PATHS`, jq가 필요하지 않습니다.
설치 위치는 실행기 자신의 경로로 찾고 파일 경로는 공백으로 분리하지 않습니다.

## 자동 실행 범위

- `PostToolUse`에서 `apply_patch`가 추가·수정한 Java 파일을 포맷팅합니다.
  기존 Claude `Edit|Write` 훅에 대응하며, 이동은 도착 경로를 처리합니다.
- 패치에 명시된 파일만 처리하고 저장소를 탐색하지 않습니다. 삭제와 비Java 파일은 제외합니다.
- Plan 모드와 실패가 보고된 도구 호출은 처리하지 않습니다.
- 셸 명령, 외부 편집기, MCP 도구를 통한 수정은 자동 감지하지 않습니다. 이때는 스킬로 실행합니다.
- 변경된 파일 목록을 Codex에 전달해 다시 읽도록 합니다. 변경이 없으면 훅은 조용히 종료합니다.
- 훅은 동기 실행됩니다. 내부 실행 제한은 540초, 훅 제한은 600초입니다.
- 실행 실패는 오류로 보고합니다. 여러 파일 중 일부가 이미 포맷팅된 후 실패할 수 있으며
  자동 롤백하지 않습니다. 자동 훅 오류는 완료된 원래 패치를 취소하지 않습니다.

## 포맷 규칙과 유지보수

Eclipse 포맷팅 외에도 import 정리, 중괄호 추가, enum 상수 배치, 메서드 체이닝과
한 줄 `/** ... */` 주석 후처리가 적용됩니다. 결과를 diff로 확인하세요.

`EclipseFormatter.java`, `eclipse-formatter.xml`, `.tool-versions`는 기존 플러그인에서
가져온 독립 사본입니다. 규칙을 업데이트할 때 양쪽을 비교해야 합니다.
Java 포맷 알고리즘은 동일하고, Codex 사본은 파일별 예외와 잘못된 파일을 비정상 종료로
전달하도록 진입점의 오류 처리만 보완했습니다.

## 로컬 검증

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s plugins/gpt-java-formatter/tests -v
jq empty plugins/gpt-java-formatter/.codex-plugin/plugin.json plugins/gpt-java-formatter/hooks/hooks.json
```

단위 테스트는 프로젝트 안에 임시 파일을 만들고 가짜 jbang으로 경로 전달·파일 선택·응답·실패
처리를 검증합니다. 실제 엔진 검증은 다음 명령으로 실행합니다.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 plugins/gpt-java-formatter/tests/smoke_formatter.py
```

Codex에 설치한 뒤에는 `apply_patch`로 Java 파일을 수정하여 자동 포맷팅과 변경 알림을
확인하고, 비Java 파일 편집에서는 포맷터가 실행되지 않는지 확인합니다.

참고: [Codex 훅 입력·출력과 신뢰 설정](https://learn.chatgpt.com/docs/hooks),
[Codex 플러그인 패키징](https://developers.openai.com/plugins/build/plugins).
