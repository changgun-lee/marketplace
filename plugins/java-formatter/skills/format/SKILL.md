---
name: format
description: Eclipse formatter와 후처리 작업용 프로그램을 사용하여 Java 파일을 포맷팅합니다
---

## 사용법

Java 파일을 Eclipse 코드 스타일로 포맷팅합니다.

## 실행 방법

```bash
CLAUDE_FILE_PATHS="<java_file_paths>" ${CLAUDE_PLUGIN_ROOT}/java-formatter.sh
```

- `<java_file_paths>`: 포맷팅할 Java 파일 경로 (공백으로 구분하여 여러 파일 지정 가능)

## 예시

```bash
# 단일 파일 포맷팅
CLAUDE_FILE_PATHS="/path/to/MyClass.java" ${CLAUDE_PLUGIN_ROOT}/java-formatter.sh

# 여러 파일 포맷팅
CLAUDE_FILE_PATHS="/path/to/File1.java /path/to/File2.java" ${CLAUDE_PLUGIN_ROOT}/java-formatter.sh
```

## 필수 조건

- jbang이 설치되어 있어야 합니다 (`brew install jbang`)
- Eclipse formatter 설정 파일: `${CLAUDE_PLUGIN_ROOT}/eclipse-formatter.xml`

## 설정 파일

Eclipse formatter 설정은 `${CLAUDE_PLUGIN_ROOT}/eclipse-formatter.xml`에서 커스터마이징할 수 있습니다.
