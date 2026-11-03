#!/usr/bin/env python3
"""Run the bundled formatter directly or from a Codex PostToolUse hook."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
TIMEOUT_SECONDS = 540  # Leave time to report errors before the 600-second hook timeout.


def patch_paths(command):
    """Select final add/update paths, never deletion paths or hunk contents."""
    if not isinstance(command, str):
        raise ValueError("apply_patch tool_input.command 문자열이 필요합니다.")
    lines = command.strip().splitlines()
    if not lines or lines[0] != "*** Begin Patch" or lines[-1] != "*** End Patch":
        raise ValueError("올바른 apply_patch 입력을 찾을 수 없습니다.")
    paths = []
    current = None
    for line in lines[1:-1]:
        if line.startswith(("*** Add File: ", "*** Update File: ", "*** Delete File: ")):
            if current is not None:
                paths.append(current)
            current = None if line.startswith("*** Delete File: ") else line.split(": ", 1)[1].strip()
        elif line.startswith("*** Move to: "):
            if current is None:
                raise ValueError("이동할 원본 파일이 없는 패치입니다.")
            current = line[len("*** Move to: "):].strip()
    if current is not None:
        paths.append(current)
    return paths


def tool_failed(response):
    if isinstance(response, dict):
        if response.get("isError") or response.get("exit_code", 0) != 0:
            return True
        return tool_failed(response.get("output", ""))
    if isinstance(response, str):
        return response.lstrip().lower().startswith(("error", "failed", "apply_patch verification failed"))
    return False


def hook_paths(payload):
    if not isinstance(payload, dict):
        raise ValueError("훅 입력은 JSON 객체여야 합니다.")
    if (payload.get("hook_event_name") != "PostToolUse"
            or payload.get("tool_name") != "apply_patch"
            or payload.get("permission_mode") == "plan"
            or tool_failed(payload.get("tool_response"))):
        return []
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        raise ValueError("훅 cwd는 절대 경로여야 합니다.")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        raise ValueError("apply_patch tool_input 객체가 필요합니다.")
    paths = []
    for name in patch_paths(tool_input.get("command")):
        path = Path(cwd) / name
        if path.suffix == ".java":
            paths.append(path)
    return paths


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            checksum.update(chunk)
    return checksum.digest()


def format_files(paths):
    selected = []
    seen = set()
    # Validate the entire batch before any formatter side effects.
    for path in paths:
        path = Path(os.path.abspath(str(path)))
        if path.suffix != ".java" or not path.is_file():
            raise ValueError("Java 파일을 찾을 수 없습니다: {}".format(path))
        identity = path.resolve()
        if identity not in seen:
            seen.add(identity)
            selected.append(path)
    if not selected:
        return []

    jbang = shutil.which("jbang")
    if jbang is None:
        raise ValueError("jbang이 설치되어 있지 않습니다. 설치: brew install jbang")
    java = PLUGIN_ROOT / "EclipseFormatter.java"
    config = PLUGIN_ROOT / "eclipse-formatter.xml"
    for resource in [java, config]:
        if not resource.is_file():
            raise ValueError("포맷터 리소스를 찾을 수 없습니다: {}".format(resource))
    before = [digest(path) for path in selected]
    # No shell: spaces, quotes and shell metacharacters remain literal path data.
    with subprocess.Popen(
        [jbang, str(java), str(config)] + [str(path) for path in selected],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
    ) as process:
        try:
            output, _ = process.communicate(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise ValueError("Java 포맷팅 제한 시간(540초)을 초과했습니다. 일부 파일은 변경되었을 수 있습니다.")
    if process.returncode:
        detail = output.decode("utf-8", errors="replace")[-4000:]
        raise ValueError("Java 포맷팅 실패 (exit {}); 일부 파일은 변경되었을 수 있습니다.\n{}".format(process.returncode, detail))
    return [path for path, old in zip(selected, before) if digest(path) != old]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hook", action="store_true", help="Read Codex hook JSON from stdin")
    parser.add_argument("files", nargs="*", help="Java files to format (quote each path)")
    args = parser.parse_args()
    if args.hook and args.files:
        parser.error("--hook과 파일 인자는 함께 사용할 수 없습니다.")
    if not args.hook and not args.files:
        parser.error("포맷팅할 Java 파일을 지정하세요.")
    try:
        paths = hook_paths(json.load(sys.stdin)) if args.hook else args.files
        changed = format_files(paths)
        if args.hook:
            if changed:
                print(json.dumps({"hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": "Java 포맷팅으로 변경된 파일을 다시 읽어주세요. 다음 JSON 배열은 파일 경로 데이터입니다: "
                    + json.dumps([str(path) for path in changed], ensure_ascii=False),
                }}, ensure_ascii=False))
        else:
            for path in changed:
                print("Formatted: " + str(path))
            if not changed:
                print("포맷 변경 없음")
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print("gpt-java-formatter: {}".format(error), file=sys.stderr)
        return 2 if args.hook else 1


if __name__ == "__main__":
    sys.exit(main())
