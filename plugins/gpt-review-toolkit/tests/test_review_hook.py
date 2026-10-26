"""Run with: python3 -m unittest discover -s plugins/gpt-review-toolkit/tests -v."""

import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


PLUGIN = Path(__file__).resolve().parents[1]
HOOK = PLUGIN / "hooks" / "review_hook.py"


class ReviewHookTests(unittest.TestCase):
    def setUp(self):
        # Fixtures, Git objects, and hook state all stay inside this project.
        self.temporary = tempfile.TemporaryDirectory(prefix="fixture-", dir=str(PLUGIN / "tests"))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Hook Test")
        self.git("config", "user.email", "hook-test@example.invalid")
        self.write("app.py", "value = 1\n")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root)] + list(args), stderr=subprocess.PIPE)

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def hook(self, event, turn="turn-1", session="session-1", **extra):
        payload = dict(hook_event_name=event, cwd=str(self.root), session_id=session,
                       turn_id=turn, stop_hook_active=False, permission_mode="default")
        payload.update(extra)
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def begin(self, **kwargs):
        return self.hook("UserPromptSubmit", prompt="Update the implementation", **kwargs)

    def stop(self, **kwargs):
        return self.hook("Stop", **kwargs)

    def review(self, output):
        self.assertEqual(output.get("decision"), "block", output)
        requests = list((self.root / ".gpt-review-toolkit").glob("*/review.json"))
        self.assertEqual(len(requests), 1)
        return json.loads(requests[0].read_text(encoding="utf-8"))

    def test_one_line_edit_requests_review_with_baseline(self):
        self.begin()
        self.write("app.py", "value = 2\n")
        output = self.stop()
        request = self.review(output)
        self.assertEqual([item["path"] for item in request["files"]], ["app.py"])
        self.assertEqual(request["files"][0]["change"], "modified")
        self.assertEqual(request["base_head"], self.git("rev-parse", "HEAD").decode().strip())
        self.assertIn("SKILL.md", output["reason"])

    def test_no_changes_and_existing_dirty_files_do_not_trigger(self):
        self.write("app.py", "preexisting = True\n")
        self.write("untracked.py", "preexisting = True\n")
        self.begin()
        self.assertNotIn("decision", self.stop())

    def test_non_source_only_changes_do_not_trigger(self):
        files = ("README.md", "settings.json", "ci.yml", "build.gradle", "build.gradle.kts",
                 "settings.gradle.kts", "buildSrc/conventions.gradle.kts", "Makefile",
                 "Dockerfile", "assets/logo.svg", "tests/fixture.json", "src/notes.txt")
        for name in files:
            self.write(name, "before\n")
        self.git("add", ".")
        self.git("commit", "-qm", "non-source fixtures")
        for operation in ("modified", "deleted", "added"):
            with self.subTest(operation=operation):
                self.begin(turn=operation)
                for name in files:
                    if operation == "deleted":
                        (self.root / name).unlink()
                    else:
                        self.write(name, operation + "\n")
                self.assertEqual(self.stop(turn=operation), {})
                self.assertEqual(list((self.root / ".gpt-review-toolkit").glob("*/review.json")), [])

    def test_existing_dirty_code_does_not_enable_document_only_review(self):
        self.write("app.py", "preexisting = True\n")
        self.begin()
        self.write("README.md", "new documentation\n")
        self.assertEqual(self.stop(), {})

    def test_code_and_document_changes_are_reviewed_together(self):
        self.begin()
        self.write("app.py", "value = 2\n")
        self.write("README.md", "new documentation\n")
        request = self.review(self.stop())
        self.assertEqual([item["path"] for item in request["files"]], ["README.md", "app.py"])

    def test_source_test_and_script_additions_trigger(self):
        for name in ("src/Main.java", "src/App.tsx", "tests/test_app.py", "scripts/check.sh", "scripts/check.kts"):
            with self.subTest(name=name):
                self.begin(turn=name)
                self.write(name, "// new source\n")
                request = self.review(self.stop(turn=name))
                self.assertEqual([item["path"] for item in request["files"]], [name])

    def test_extensionless_script_changes_use_before_and_after_shebang(self):
        name = "bin/check"
        for operation in ("added", "modified", "removed-shebang", "restored-shebang", "deleted"):
            with self.subTest(operation=operation):
                self.begin(turn=operation)
                if operation == "deleted":
                    (self.root / name).unlink()
                elif operation == "removed-shebang":
                    self.write(name, "echo changed\n")
                else:
                    self.write(name, "#!/bin/sh\necho " + operation + "\n")
                request = self.review(self.stop(turn=operation))
                self.assertEqual([item["path"] for item in request["files"]], [name])

    def test_executable_non_script_does_not_trigger(self):
        self.begin()
        self.write("binary", "not a script\n")
        (self.root / "binary").chmod(0o755)
        self.assertEqual(self.stop(), {})

    def test_new_deleted_and_renamed_files_are_included(self):
        self.begin()
        (self.root / "app.py").rename(self.root / "renamed.py")
        self.write("new file\n한글.py", "created = True\n")
        request = self.review(self.stop())
        changes = {item["path"]: item["change"] for item in request["files"]}
        self.assertEqual(changes, {"app.py": "deleted", "renamed.py": "added", "new file\n한글.py": "added"})

    def test_staged_and_committed_changes_are_still_reviewed(self):
        for commit in (False, True):
            with self.subTest(commit=commit):
                turn = "commit-" + str(commit)
                original_head = self.git("rev-parse", "HEAD").decode().strip()
                self.begin(turn=turn)
                self.write("app.py", "committed = {!r}\n".format(commit))
                self.git("add", "app.py")
                if commit:
                    self.git("commit", "-qm", "update")
                request = self.review(self.stop(turn=turn))
                self.assertEqual(request["files"][0]["path"], "app.py")
                self.assertEqual(request["base_head"], original_head)
                if commit:
                    self.assertNotEqual(request["base_head"], request["head"])

    def test_staging_without_content_change_does_not_trigger(self):
        self.write("app.py", "preexisting = True\n")
        self.begin()
        self.git("add", "app.py")
        self.assertNotIn("decision", self.stop())

    def test_changed_existing_dirty_file_preserves_before_content(self):
        self.write("app.py", "before = 10\n")
        self.begin()
        self.write("app.py", "after = 20\n")
        request = self.review(self.stop())
        self.assertEqual(request["files"][0]["before"]["text"], "before = 10\n")

    def test_repeated_stop_and_hook_continuation_do_not_repeat_review(self):
        self.begin()
        self.write("app.py", "value = 2\n")
        first = self.stop()
        self.review(first)
        self.assertNotIn("decision", self.stop())
        self.assertNotIn("decision", self.stop(stop_hook_active=True))
        self.hook("UserPromptSubmit", turn="continuation", prompt=first["reason"])
        self.assertNotIn("decision", self.stop(turn="continuation", stop_hook_active=True))
        self.begin(turn="next-user-turn")
        self.assertNotIn("decision", self.stop(turn="next-user-turn"))
        self.begin(turn="another-user-turn")
        self.write("app.py", "value = 3\n")
        self.review(self.stop(turn="another-user-turn"))

    def test_changes_after_a_requested_review_can_trigger_again(self):
        self.begin()
        self.write("app.py", "value = 2\n")
        self.review(self.stop())
        self.write("app.py", "value = 3\n")
        self.review(self.stop())

    def test_reverted_content_and_touch_only_do_not_trigger(self):
        self.begin()
        self.write("app.py", "temporary = True\n")
        self.write("app.py", "value = 1\n")
        self.assertNotIn("decision", self.stop())

    def test_mode_change_is_reviewed(self):
        self.begin()
        (self.root / "app.py").chmod(0o755)
        self.assertEqual(self.review(self.stop())["files"][0]["change"], "modified")

    def test_symlinks_are_not_followed(self):
        outside = PLUGIN / "tests" / "symlink-target-does-not-exist"
        (self.root / "link.py").symlink_to(outside)
        self.begin()
        (self.root / "link.py").unlink()
        (self.root / "link.py").symlink_to("another-target")
        request = self.review(self.stop())
        self.assertEqual(request["files"][0]["path"], "link.py")

    def test_ignored_files_and_hook_state_are_not_reviewed(self):
        self.write(".gitignore", "build/\n")
        self.git("add", ".gitignore")
        self.git("commit", "-qm", "ignore build")
        self.begin()
        self.write("build/output.py", "generated = True\n")
        self.assertNotIn("decision", self.stop())
        self.assertEqual(self.git("status", "--porcelain"), b"")

    def test_missing_baseline_is_reported_without_reviewing_old_changes(self):
        self.write("app.py", "preexisting = True\n")
        output = self.stop()
        self.assertNotIn("decision", output)
        self.assertIn("systemMessage", output)

    def test_stale_turn_cannot_use_another_turns_baseline(self):
        self.begin(turn="old")
        self.write("app.py", "value = 2\n")
        self.begin(turn="new")
        self.assertNotIn("decision", self.stop(turn="old"))

    def test_plan_mode_does_not_trigger_review(self):
        self.begin(permission_mode="plan")
        self.write("app.py", "value = 2\n")
        self.assertNotIn("decision", self.stop(permission_mode="plan"))

    def test_non_git_workspace_reports_unavailable_detection(self):
        plain = self.root / "plain"
        plain.mkdir()
        # Disallow discovery of the enclosing fixture repository.
        result = subprocess.run([sys.executable, str(HOOK)],
                                input=json.dumps(dict(hook_event_name="UserPromptSubmit", cwd=str(plain),
                                                      session_id="s", turn_id="t")),
                                env=dict(os.environ, GIT_CEILING_DIRECTORIES=str(self.root)),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("systemMessage", json.loads(result.stdout))

    def test_worktree_state_stays_inside_worktree(self):
        linked = self.root / "linked"
        self.git("worktree", "add", "-qb", "linked", str(linked))
        self.begin(cwd=str(linked))
        (linked / "app.py").write_text("value = 2\n", encoding="utf-8")
        self.assertEqual(self.stop(cwd=str(linked)).get("decision"), "block")
        self.assertTrue((linked / ".gpt-review-toolkit").is_dir())
        self.assertFalse((self.root / ".git" / "gpt-review-toolkit").exists())

    def test_sessions_do_not_overwrite_each_others_baselines(self):
        self.begin(session="a")
        self.write("app.py", "value = 2\n")
        self.begin(session="b")
        self.assertEqual(self.stop(session="a").get("decision"), "block")
        self.assertNotIn("decision", self.stop(session="b"))

    def test_no_commit_yet_is_supported(self):
        self.git("update-ref", "-d", "HEAD")
        self.begin()
        self.write("app.py", "value = 2\n")
        request = self.review(self.stop())
        self.assertIsNone(request["base_head"])
        self.assertEqual(request["files"][0]["before"]["text"], "value = 1\n")

    def test_binary_and_large_dirty_before_contents_are_marked_unavailable(self):
        (self.root / "binary").write_bytes(b"before\x00binary")
        self.write("large", "x" * (1024 * 1024 + 1))
        self.begin()
        (self.root / "binary").write_bytes(b"after\x00binary")
        self.write("large", "y" * (1024 * 1024 + 1))
        self.write("app.py", "value = 2\n")
        request = self.review(self.stop())
        for item in request["files"]:
            if item["path"] == "app.py":
                continue
            self.assertIn("before_unavailable", item["before"])
            self.assertNotIn("text", item["before"])

    def test_state_symlink_is_rejected_without_writing_to_target(self):
        target = self.root / "other"
        target.mkdir()
        (self.root / ".gpt-review-toolkit").symlink_to(target)
        output = self.begin()
        self.assertIn("systemMessage", output)
        self.assertEqual(list(target.iterdir()), [])

    def test_malformed_json_is_reported_as_warning(self):
        result = subprocess.run([sys.executable, str(HOOK)], input="invalid-json",
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("systemMessage", json.loads(result.stdout))

    def test_corrupt_baseline_is_reported_as_warning(self):
        self.begin()
        baseline = next((self.root / ".gpt-review-toolkit").glob("*/baseline.json"))
        baseline.write_text("corrupt", encoding="utf-8")
        self.assertIn("systemMessage", self.stop())

    def test_new_ignore_rule_does_not_report_existing_file_as_deleted(self):
        self.write("existing.py", "unchanged = True\n")
        self.begin()
        self.write(".gitignore", "existing.py\n")
        self.assertEqual(self.stop(), {})

    def test_removing_ignored_file_from_index_is_not_a_content_change(self):
        self.write(".gitignore", "app.py\n")
        self.git("add", ".gitignore")
        self.git("commit", "-qm", "ignore app")
        self.begin()
        self.git("rm", "--cached", "app.py")
        self.assertNotIn("decision", self.stop())

    def test_unchanged_large_and_binary_files_reuse_content_hash(self):
        spec = importlib.util.spec_from_file_location("review_hook", str(HOOK))
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        for name, content in (("large", b"x" * (1024 * 1024 + 1)), ("binary", b"x\x00y")):
            with self.subTest(name=name):
                path = self.root / name
                path.write_bytes(content)
                cached = hook.fingerprint_file(path, {}, capture_text=True)
                # Reading is unnecessary when metadata is identical and text cannot be captured.
                with mock.patch.object(Path, "open", side_effect=AssertionError("unchanged file reread")):
                    again = hook.fingerprint_file(path, cached, capture_text=True)
                self.assertEqual(again["sha256"], cached["sha256"])

    def test_manifest_hook_commands_work_with_spaces_in_plugin_root(self):
        installed = self.root / "plugin with spaces"
        installed.symlink_to(PLUGIN)
        manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
        config = json.loads((PLUGIN / manifest["hooks"]).read_text())
        env = dict(os.environ, PLUGIN_ROOT=str(installed))
        for event in ("UserPromptSubmit", "Stop"):
            if event == "Stop":
                self.write("app.py", "value = 2\n")
            payload = dict(hook_event_name=event, cwd=str(self.root), session_id="s", turn_id="t")
            command = config["hooks"][event][0]["hooks"][0]["command"]
            result = subprocess.run(["bash", "-c", command], input=json.dumps(payload), env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            if event == "Stop":
                self.assertEqual(output.get("decision"), "block", output)


class WorkspaceReviewHookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="workspace-", dir=str(PLUGIN / "tests"))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        # Keep the fixture inside the project without discovering its enclosing Git repo.
        self.env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(self.root.parent))

    def repository(self, name):
        root = self.root / name
        root.mkdir(parents=True)
        for args in (("init", "-q"), ("config", "user.name", "Hook Test"),
                     ("config", "user.email", "hook-test@example.invalid")):
            subprocess.check_call(["git", "-C", str(root)] + list(args), env=self.env)
        (root / "app.py").write_text("value = 1\n", encoding="utf-8")
        return root

    def hook(self, event, **extra):
        payload = dict(hook_event_name=event, cwd=str(self.root), session_id="s", turn_id="t")
        payload.update(extra)
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), env=self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def request(self, root, output):
        requests = list((root / ".gpt-review-toolkit").glob("*/review.json"))
        self.assertEqual(len(requests), 1, output)
        self.assertIn(json.dumps(str(requests[0]), ensure_ascii=False), output["reason"])
        request = json.loads(requests[0].read_text(encoding="utf-8"))
        self.assertEqual(request["project_root"], str(root))
        return request

    def test_all_direct_repositories_are_reviewed_with_separate_baselines(self):
        first = self.repository("first repo")
        second = self.repository("두번째\nrepo")
        self.assertEqual(self.hook("UserPromptSubmit"), {})
        for index, root in enumerate((first, second)):
            (root / "app.py").write_text("value = {}\n".format(index + 2), encoding="utf-8")
        output = self.hook("Stop")
        self.assertEqual(output.get("decision"), "block", output)
        for root in (first, second):
            request = self.request(root, output)
            self.assertEqual([item["path"] for item in request["files"]], ["app.py"])
            self.assertEqual(request["files"][0]["before"]["text"], "value = 1\n")
        self.assertEqual(self.hook("Stop"), {})
        self.assertEqual(self.hook("Stop", stop_hook_active=True), {})
        (second / "app.py").write_text("value = 4\n", encoding="utf-8")
        subsequent = self.hook("Stop")
        self.request(second, subsequent)
        self.assertNotIn(json.dumps(str(first), ensure_ascii=False), subsequent["reason"])

    def test_only_repositories_with_source_changes_request_review(self):
        source = self.repository("source")
        documents = self.repository("documents")
        unchanged = self.repository("unchanged")
        self.assertEqual(self.hook("UserPromptSubmit"), {})
        self.assertEqual(self.hook("Stop"), {})
        (source / "app.py").write_text("value = 2\n", encoding="utf-8")
        (documents / "README.md").write_text("documentation\n", encoding="utf-8")
        output = self.hook("Stop")
        self.request(source, output)
        for root in (documents, unchanged):
            self.assertEqual(list((root / ".gpt-review-toolkit").glob("*/review.json")), [])

    def test_discovery_does_not_recurse_or_follow_directory_symlinks(self):
        direct = self.repository("direct")
        nested = self.repository("container/nested")
        (self.root / "linked-repo").symlink_to(nested, target_is_directory=True)
        self.assertEqual(self.hook("UserPromptSubmit"), {})
        self.assertFalse((nested / ".gpt-review-toolkit").exists())
        (nested / "app.py").write_text("value = 2\n", encoding="utf-8")
        self.assertEqual(self.hook("Stop"), {})
        self.assertTrue((direct / ".gpt-review-toolkit").is_dir())

    def test_existing_git_repository_takes_precedence_over_children(self):
        root = self.repository("project")
        nested = self.repository("project/nested")
        self.assertEqual(self.hook("UserPromptSubmit", cwd=str(root)), {})
        self.assertFalse((nested / ".gpt-review-toolkit").exists())
        (root / "app.py").write_text("value = 2\n", encoding="utf-8")
        self.request(root, self.hook("Stop", cwd=str(root)))

    def test_direct_worktrees_are_supported(self):
        origin = self.repository("container/origin")
        for args in (("add", "."), ("commit", "-qm", "initial"),
                     ("worktree", "add", "-qb", "linked", str(self.root / "linked"))):
            subprocess.check_call(["git", "-C", str(origin)] + list(args), env=self.env)
        linked = self.root / "linked"
        self.assertEqual(self.hook("UserPromptSubmit"), {})
        (linked / "app.py").write_text("value = 2\n", encoding="utf-8")
        self.request(linked, self.hook("Stop"))
        self.assertFalse((origin / ".gpt-review-toolkit").exists())

    def test_repository_failure_does_not_prevent_other_reviews(self):
        broken = self.repository("a-broken")
        healthy = self.repository("z-healthy")
        self.assertEqual(self.hook("UserPromptSubmit"), {})
        baseline = next((broken / ".gpt-review-toolkit").glob("*/baseline.json"))
        baseline.write_text("corrupt", encoding="utf-8")
        (healthy / "app.py").write_text("value = 2\n", encoding="utf-8")
        output = self.hook("Stop")
        self.assertIn(str(broken), output.get("systemMessage", ""))
        self.request(healthy, output)

    def test_invalid_child_git_metadata_is_reported_without_skipping_healthy_repo(self):
        broken = self.root / "a-broken"
        broken.mkdir()
        (broken / ".git").write_text("invalid git file\n", encoding="utf-8")
        healthy = self.repository("z-healthy")
        started = self.hook("UserPromptSubmit")
        self.assertIn(str(broken), started.get("systemMessage", ""))
        (healthy / "app.py").write_text("value = 2\n", encoding="utf-8")
        output = self.hook("Stop")
        self.assertIn(str(broken), output.get("systemMessage", ""))
        self.request(healthy, output)

    def test_discovery_timeout_does_not_prevent_other_reviews(self):
        broken = self.repository("a-timeout")
        healthy = self.repository("z-healthy")
        spec = importlib.util.spec_from_file_location("review_hook", str(HOOK))
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        real_git = hook.git

        def timeout_for_broken(root, *args, **kwargs):
            if root == broken:
                raise subprocess.TimeoutExpired("git", 15)
            return real_git(root, *args, **kwargs)

        payload = dict(cwd=str(self.root), session_id="s", turn_id="t")
        # Inject only the slow process failure; healthy discovery and snapshots use real Git.
        with mock.patch.dict(os.environ, self.env), mock.patch.object(hook, "git", timeout_for_broken):
            started = hook.handle(dict(payload, hook_event_name="UserPromptSubmit"))
            self.assertIn(str(broken), started.get("systemMessage", ""))
            (healthy / "app.py").write_text("value = 2\n", encoding="utf-8")
            output = hook.handle(dict(payload, hook_event_name="Stop"))
        self.assertIn(str(broken), output.get("systemMessage", ""))
        self.request(healthy, output)

    def test_repositories_added_or_removed_during_turn_are_reported(self):
        removed = self.repository("removed")
        healthy = self.repository("healthy")
        self.assertEqual(self.hook("UserPromptSubmit"), {})
        # Move it beyond the one-level discovery boundary, without deleting fixture data.
        (self.root / "archive").mkdir()
        removed.rename(self.root / "archive" / "removed")
        added = self.repository("added")
        (healthy / "app.py").write_text("value = 2\n", encoding="utf-8")
        output = self.hook("Stop")
        self.assertIn(str(removed), output.get("systemMessage", ""))
        self.assertIn(str(added), output.get("systemMessage", ""))
        self.request(healthy, output)


if __name__ == "__main__":
    unittest.main()
