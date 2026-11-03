import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
RUNNER = PLUGIN / "scripts" / "format_java.py"


class FormatterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="formatter-test-", dir=REPO)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "args.json"
        fake = self.bin / "jbang"
        fake.write_text(
            "#!" + sys.executable + "\n"
            "import json, os, pathlib, sys\n"
            "pathlib.Path(os.environ['FORMATTER_TEST_LOG']).write_text(json.dumps(sys.argv[1:]))\n"
            "if os.environ.get('FORMATTER_TEST_FAIL'):\n"
            "    print('formatter failed', file=sys.stderr)\n"
            "    sys.exit(7)\n"
            "for name in sys.argv[3:]:\n"
            "    path = pathlib.Path(name)\n"
            "    path.write_bytes(path.read_bytes().replace(b'UNFORMATTED', b'FORMATTED'))\n"
            "print('jbang output must not corrupt hook JSON')\n"
        )
        fake.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin), FORMATTER_TEST_LOG=str(self.log))
        self.env.pop("CLAUDE_PLUGIN_ROOT", None)
        self.env.pop("CLAUDE_FILE_PATHS", None)
        self.env.pop("PLUGIN_ROOT", None)

    def file(self, name, content="UNFORMATTED"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def run_cli(self, *paths, runner=RUNNER):
        return subprocess.run(
            [sys.executable, str(runner), *map(str, paths)], cwd=self.root,
            env=self.env, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def run_hook(self, patch, **overrides):
        payload = {
            "hook_event_name": "PostToolUse", "tool_name": "apply_patch",
            "cwd": str(self.root), "tool_input": {"command": patch},
            "tool_response": "Success. Updated the following files:\nM Example.java\n",
        }
        payload.update(overrides)
        return subprocess.run(
            [sys.executable, str(RUNNER), "--hook"], input=json.dumps(payload),
            cwd=REPO, env=self.env, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def patch(self, *headers):
        return "*** Begin Patch\n" + "\n".join(headers) + "\n*** End Patch"

    def test_cli_paths_are_separate_arguments_and_not_shell_code(self):
        first = self.file("space dir/One.java")
        second = self.file("$(touch INJECTED);'二.java")
        result = self.run_cli(first, second, first)
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(self.log.read_text())
        self.assertEqual(args[2:], [str(first), str(second)])
        self.assertEqual(first.read_text(), "FORMATTED")
        self.assertEqual(second.read_text(), "FORMATTED")
        self.assertFalse((self.root / "INJECTED").exists())

    def test_cli_validates_every_file_before_modifying(self):
        good = self.file("Good.java")
        result = self.run_cli(good, self.root / "Missing.java")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(good.read_text(), "UNFORMATTED")
        self.assertFalse(self.log.exists())

    def test_cli_rejects_non_java_and_empty_arguments(self):
        for args in [(), (self.file("notes.txt"),)]:
            with self.subTest(args=args):
                self.assertNotEqual(self.run_cli(*args).returncode, 0)
        self.assertFalse(self.log.exists())

    def test_hook_formats_add_update_and_move_destination_only(self):
        added = self.file("src/New.java")
        updated = self.file("space dir/Changed.java")
        moved = self.file("new/Renamed.java")
        deleted = self.file("Deleted.java")  # deletion headers must never select this
        untouched = self.file("Untouched.java")
        text = self.file("notes.txt")
        result = self.run_hook(self.patch(
            "*** Add File: src/New.java", "+class New {}",
            "*** Update File: space dir/Changed.java", "@@", "-old", "+new",
            "*** Update File: old/Before.java", "*** Move to: new/Renamed.java",
            "@@", "-old", "+new", "*** Delete File: Deleted.java",
            "*** Update File: notes.txt", "@@", "-old", "+new",
        ))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.log.read_text())[2:], list(map(str, [added, updated, moved])))
        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PostToolUse")
        for path in [added, updated, moved]:
            self.assertEqual(path.read_text(), "FORMATTED")
            self.assertIn(str(path), output["additionalContext"])
        for path in [deleted, untouched, text]:
            self.assertEqual(path.read_text(), "UNFORMATTED")

    def test_hook_no_change_is_silent(self):
        self.file("Stable.java", "FORMATTED")
        result = self.run_hook(self.patch("*** Update File: Stable.java"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_nonmatching_event_tool_plan_and_non_java_are_noops(self):
        self.file("Example.java")
        patch = self.patch("*** Update File: Example.java")
        for overrides in [
            {"hook_event_name": "Stop"}, {"tool_name": "Bash"},
            {"permission_mode": "plan"},
            {"tool_response": {"exit_code": 1, "output": "failed"}},
            {"tool_response": {"isError": True}},
            {"tool_response": "Failed to find expected lines in Example.java"},
            {"tool_response": "apply_patch verification failed: invalid patch: multiple operations target Example.java"},
        ]:
            with self.subTest(overrides=overrides):
                result = self.run_hook(patch, **overrides)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertFalse(self.log.exists())
        self.assertEqual(self.run_hook(self.patch("*** Update File: notes.txt")).stdout, "")
        self.assertFalse(self.log.exists())

    def test_missing_dependency_is_reported_for_cli_and_hook(self):
        self.file("Example.java")
        (self.bin / "jbang").unlink()
        cli = self.run_cli("Example.java")
        hook = self.run_hook(self.patch("*** Update File: Example.java"))
        for result in [cli, hook]:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("jbang", result.stderr)

    def test_formatter_failure_is_reported_for_cli_and_hook(self):
        self.file("Example.java")
        self.env["FORMATTER_TEST_FAIL"] = "1"
        for result in [self.run_cli("Example.java"), self.run_hook(self.patch("*** Update File: Example.java"))]:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("formatter failed", result.stderr)

    def test_invalid_hook_input_fails_visibly(self):
        for raw in ["not json", "[]", "null"]:
            result = subprocess.run(
                [sys.executable, str(RUNNER), "--hook"], input=raw,
                cwd=self.root, env=self.env, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 2)
            self.assertTrue(result.stderr)
        result = self.run_hook("not a patch")
        self.assertEqual(result.returncode, 2)

    def test_plugin_is_relocatable_without_original_plugin(self):
        target = self.root / "installed plugin"
        shutil.copytree(PLUGIN, target, ignore=shutil.ignore_patterns("__pycache__"))
        java = self.file("Example.java")
        result = self.run_cli(java, runner=target / "scripts" / "format_java.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(self.log.read_text())
        self.assertEqual(args[:2], [str(target / "EclipseFormatter.java"), str(target / "eclipse-formatter.xml")])
        self.assertTrue(Path(args[0]).is_file())
        self.assertTrue(Path(args[1]).is_file())


if __name__ == "__main__":
    unittest.main()
