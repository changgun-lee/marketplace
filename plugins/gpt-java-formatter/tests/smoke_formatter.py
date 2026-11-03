#!/usr/bin/env python3
"""Exercise real jbang; keep sources, JVM temp files and caches inside this repo."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
RUNNER = PLUGIN / "scripts" / "format_java.py"
SAMPLE = """package example;
public class Example{
/** 설명 */
public void run(boolean ok){if(ok)System.out.println("ok");}
public java.util.List<String> names(){return java.util.List.of("a","b");}
enum State { FIRST, SECOND }
}
"""


def main():
    with tempfile.TemporaryDirectory(prefix="formatter-smoke-", dir=REPO) as directory:
        root = Path(directory)
        temp = root / "tmp"
        temp.mkdir()
        env = dict(os.environ)
        env.update({
            "JBANG_DIR": str(root / "jbang"),
            "JBANG_CACHE_DIR": str(root / "jbang" / "cache"),
            "JBANG_REPO": str(root / "maven"),
            "TMPDIR": str(temp),
            "JAVA_TOOL_OPTIONS": '-Duser.home="{}" -Djava.io.tmpdir="{}" -XX:-UsePerfData'.format(root, temp),
        })
        for key in ["CLAUDE_PLUGIN_ROOT", "CLAUDE_FILE_PATHS", "PLUGIN_ROOT"]:
            env.pop(key, None)

        def run(args, data=None):
            return subprocess.run(
                args, input=data, cwd=str(root), env=env, universal_newlines=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=590,
            )

        source = root / "space dir" / "Example.java"
        source.parent.mkdir()
        source.write_text(SAMPLE, encoding="utf-8")
        special = root / "$(touch INJECTED);'二.java"
        special.write_text(SAMPLE, encoding="utf-8")
        result = run([sys.executable, str(RUNNER), str(source), str(special)])
        assert result.returncode == 0, result.stderr
        formatted = source.read_text(encoding="utf-8")
        assert formatted != SAMPLE
        assert 'if (ok) {' in formatted
        assert '// 설명' in formatted
        assert 'import java.util.List;' in formatted
        assert special.read_text(encoding="utf-8") == formatted
        assert not (root / "INJECTED").exists(), "Filename was interpreted as shell code"
        second = run([sys.executable, str(RUNNER), str(source)])
        assert second.returncode == 0, second.stderr
        assert source.read_text(encoding="utf-8") == formatted, "Second run was not stable"
        print("PASS real CLI: imports, braces, comments, special paths, multiple files, idempotence", flush=True)

        # Compare output to the original engine, when running from the marketplace checkout.
        original = REPO / "plugins" / "java-formatter"
        if original.is_dir():
            baseline = root / "Baseline.java"
            baseline.write_text(SAMPLE, encoding="utf-8")
            result = run(["jbang", str(original / "EclipseFormatter.java"),
                          str(original / "eclipse-formatter.xml"), str(baseline)])
            assert result.returncode == 0, result.stderr
            assert baseline.read_text(encoding="utf-8") == formatted, "Original formatting changed"
            print("PASS original formatter equivalence", flush=True)

        source.write_text(SAMPLE, encoding="utf-8")
        payload = {
            "hook_event_name": "PostToolUse", "tool_name": "apply_patch", "cwd": str(root),
            "tool_input": {"command": "*** Begin Patch\n*** Update File: space dir/Example.java\n@@\n-old\n+new\n*** End Patch"},
            "tool_response": "Success. Updated the following files:\nM space dir/Example.java",
        }
        result = run([sys.executable, str(RUNNER), "--hook"], json.dumps(payload))
        assert result.returncode == 0, result.stderr
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        assert str(source) in context
        assert source.read_text(encoding="utf-8") == formatted
        print("PASS real PostToolUse input and JSON output", flush=True)

        broken = root / "Unreadable.java"
        broken.write_bytes(b"\xff\xfe\xff")
        result = run([sys.executable, str(RUNNER), str(broken)])
        assert result.returncode != 0, "Java per-file exception reported as success"
        assert "Error formatting" in result.stderr
        print("PASS real Java per-file failure reporting", flush=True)


if __name__ == "__main__":
    main()
