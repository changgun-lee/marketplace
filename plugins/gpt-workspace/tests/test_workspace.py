import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
RUNNER = PLUGIN / "scripts" / "make_workspace.py"


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="workspace-test-", dir=REPO)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        config = self.root / "gitconfig"
        config.write_text("[user]\n    name = Workspace Test\n    email = workspace@example.com\n")
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=str(config), GIT_CONFIG_NOSYSTEM="1",
                        GIT_TERMINAL_PROMPT="0", LC_ALL="C", PYTHONDONTWRITEBYTECODE="1")
        for key in list(self.env):
            if key.startswith("GIT_") and key not in {
                "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "GIT_TERMINAL_PROMPT"
            }:
                self.env.pop(key)
        self.origin = self.root / "origin.git"
        self.git(self.root, "init", "--bare", "--quiet", str(self.origin))
        self.project = self.new_project("project with spaces")

    def command(self, args, cwd=None):
        return subprocess.run(list(map(str, args)), cwd=str(cwd or self.root), env=self.env,
                              universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def git(self, path, *args):
        result = self.command(["git", "-C", path, *args])
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout[:-1] if result.stdout.endswith("\n") else result.stdout

    def new_project(self, name):
        path = self.root / name
        path.mkdir(parents=True)
        self.git(path, "init", "--quiet", "-b", "develop")
        (path / "tracked.txt").write_text("base\n")
        self.git(path, "add", "tracked.txt")
        self.git(path, "commit", "--quiet", "-m", "base")
        self.git(path, "remote", "add", "origin", str(self.origin))
        self.git(path, "fetch", "--quiet", "origin")
        if not self.command(["git", "-C", path, "show-ref", "--verify", "--quiet",
                             "refs/remotes/origin/develop"]).returncode:
            self.git(path, "reset", "--hard", "origin/develop")
        else:
            self.git(path, "push", "--quiet", "-u", "origin", "develop")
        return path

    def run_workspace(self, task="sample", base="develop", root=None, *extra):
        return self.command([sys.executable, RUNNER, "--root", root or self.project,
                             "--base", base, "--task", task, *extra])

    def success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        data = json.loads(result.stdout)
        self.assertNotIn("error", data)
        return data

    def upstream(self, branch="feature/sample", project=None):
        return self.git(project or self.project, "for-each-ref", "--format=%(upstream)",
                        "refs/heads/" + branch)

    def assert_no_workspace(self, project=None, branch="feature/sample"):
        project = project or self.project
        self.assertFalse((project / ".worktrees" / branch).exists())
        result = self.command(["git", "-C", project, "show-ref", "--verify", "--quiet",
                               "refs/heads/" + branch])
        self.assertNotEqual(result.returncode, 0)

    def test_new_worktree_uses_requested_base_without_inheriting_upstream(self):
        self.git(self.project, "config", "branch.autoSetupMerge", "always")
        base = self.git(self.project, "rev-parse", "develop")
        (self.project / "tracked.txt").write_text("uncommitted\n")
        (self.project / "untracked.txt").write_text("keep me\n")
        before = self.git(self.project, "status", "--porcelain=v1")
        origin_url = self.git(self.project, "remote", "get-url", "origin")
        data = self.success(self.run_workspace(base="origin/develop"))
        worktree = self.project / ".worktrees/feature/sample"
        self.assertEqual(data["workspaces"][0]["worktree"], str(worktree))
        self.assertIsNone(data["workspaces"][0]["upstream"])
        self.assertEqual(self.git(worktree, "branch", "--show-current"), "feature/sample")
        self.assertEqual(self.git(worktree, "rev-parse", "HEAD"), base)
        self.assertEqual(self.upstream(), "")
        self.assertEqual(self.git(self.project, "branch", "--show-current"), "develop")
        self.assertEqual(self.git(self.project, "status", "--porcelain=v1"), before)
        self.assertEqual(self.git(self.project, "stash", "list"), "")
        self.assertEqual(self.git(self.project, "remote", "get-url", "origin"), origin_url)
        self.assertEqual((self.project / "tracked.txt").read_text(), "uncommitted\n")
        self.assertEqual((self.project / "untracked.txt").read_text(), "keep me\n")
        self.assertEqual(self.git(self.project, "ls-remote", "--heads", "origin",
                                  "refs/heads/feature/sample"), "")

    def test_existing_same_name_remote_is_the_only_upstream(self):
        self.git(self.project, "push", "--quiet", "origin", "develop:refs/heads/feature/sample")
        data = self.success(self.run_workspace())
        self.assertEqual(data["workspaces"][0]["upstream"], "origin/feature/sample")
        self.assertEqual(self.upstream(), "refs/remotes/origin/feature/sample")

    def test_deleted_remote_ref_does_not_become_upstream(self):
        self.git(self.project, "push", "--quiet", "origin", "develop:refs/heads/feature/sample")
        self.git(self.project, "fetch", "--quiet", "origin")
        self.git(self.root, "--git-dir=" + str(self.origin), "update-ref", "-d",
                 "refs/heads/feature/sample")
        self.success(self.run_workspace())
        self.assertEqual(self.upstream(), "")

    def test_unicode_line_separators_and_trailing_spaces_in_remote_names_are_preserved(self):
        for task in ["split\u2028line", "trailing\u00a0"]:
            with self.subTest(task=task):
                branch = "feature/" + task
                self.git(self.project, "push", "--quiet", "origin", "develop:refs/heads/" + branch)
                self.success(self.run_workspace(task=task))
                self.assertEqual(self.upstream(branch), "refs/remotes/origin/" + branch)

    def test_full_refs_avoid_ambiguous_local_remote_and_tag_names(self):
        self.git(self.project, "branch", "origin/feature/sample")
        self.git(self.project, "tag", "feature/sample")
        self.git(self.project, "push", "--quiet", "origin", "develop:refs/heads/feature/sample")
        self.success(self.run_workspace())
        self.assertEqual(self.upstream(), "refs/remotes/origin/feature/sample")
        self.assertEqual(self.git(self.project / ".worktrees/feature/sample", "symbolic-ref", "HEAD"),
                         "refs/heads/feature/sample")

    def test_normalizes_only_invalid_characters_and_patterns(self):
        cases = [
            ("로그인 API/개선", "로그인-API-개선"),
            ("a~b^c:d?e*f[g\\h", "a-b-c-d-e-f-g-h"),
            (".hidden..name@{next}.lock", "-hidden--name@-next}-lock"),
            ("trailing.", "trailing-"),
            ("two\tlines\n", "two-lines-"),
            ("Keep_대문자+ok", "Keep_대문자+ok"),
            ("valid\u00a0space\u3000name", "valid\u00a0space\u3000name"),
            ("\u00a0trailing\u3000", "\u00a0trailing\u3000"),
            ("$(touch INJECTED);'x", "$(touch-INJECTED);'x"),
        ]
        for task, suffix in cases:
            with self.subTest(task=task):
                data = self.success(self.run_workspace(task=task))
                self.assertEqual(data["branch"], "feature/" + suffix)
                target = self.project / ".worktrees/feature" / suffix
                self.assertEqual(self.git(target, "branch", "--show-current"), "feature/" + suffix)
        self.assertFalse((self.root / "INJECTED").exists())
        self.assertFalse((self.project / "INJECTED").exists())

    def test_discovers_nested_repositories_and_skips_worktree_copies(self):
        child = self.new_project("project with spaces/child")
        data = self.success(self.run_workspace())
        self.assertEqual({entry["project"] for entry in data["workspaces"]},
                         {str(self.project), str(child)})
        second = self.success(self.run_workspace(task="another"))
        self.assertEqual(len(second["workspaces"]), 2)
        self.assertFalse((self.project / ".worktrees/feature/sample/.worktrees").exists())

    def test_parent_directory_discovers_multiple_projects(self):
        second = self.new_project("second")
        data = self.success(self.run_workspace(root=self.root))
        self.assertEqual({entry["project"] for entry in data["workspaces"]},
                         {str(self.project), str(second)})

    def test_git_file_in_a_linked_checkout_is_supported(self):
        checkout = self.root / "linked"
        self.git(self.project, "worktree", "add", "--quiet", "--detach", str(checkout), "develop")
        self.assertTrue((checkout / ".git").is_file())
        data = self.success(self.run_workspace(root=checkout))
        target = checkout / ".worktrees/feature/sample"
        self.assertEqual(data["workspaces"][0]["worktree"], str(target))
        self.assertEqual(self.git(target, "branch", "--show-current"), "feature/sample")

    def test_explicit_project_selection_limits_scope(self):
        second = self.new_project("second")
        data = self.success(self.run_workspace("sample", "develop", self.root,
                                               "--project", str(second)))
        self.assertEqual([entry["project"] for entry in data["workspaces"]], [str(second)])
        self.assert_no_workspace()

    def test_dry_run_does_not_create_worktrees_branches_or_ignore_file(self):
        exclude = self.project / ".git/info/exclude"
        before = exclude.read_bytes()
        data = self.success(self.run_workspace("sample", "develop", None, "--dry-run"))
        self.assertEqual(len(data["workspaces"]), 1)
        self.assert_no_workspace()
        self.assertEqual(exclude.read_bytes(), before)

    def test_preflight_failure_in_one_project_creates_nothing_in_any_project(self):
        second = self.new_project("second")
        self.git(second, "remote", "remove", "origin")
        result = self.run_workspace(root=self.root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("origin", json.loads(result.stdout)["error"])
        self.assert_no_workspace()
        self.assert_no_workspace(second)

    def test_a_file_in_a_worktree_parent_fails_before_any_project_is_created(self):
        second = self.new_project("second")
        (second / ".worktrees").write_text("keep this file")
        result = self.run_workspace(root=self.root)
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_workspace()
        self.assert_no_workspace(second)
        self.assertEqual((second / ".worktrees").read_text(), "keep this file")

    def test_local_and_remote_base_divergence_requires_an_explicit_ref(self):
        (self.project / "local.txt").write_text("local\n")
        self.git(self.project, "add", "local.txt")
        self.git(self.project, "commit", "--quiet", "-m", "local only")
        result = self.run_workspace()
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_workspace()
        remote_commit = self.git(self.project, "rev-parse", "origin/develop")
        self.success(self.run_workspace(base="origin/develop"))
        self.assertEqual(self.git(self.project, "rev-parse", "feature/sample"), remote_commit)
        local_commit = self.git(self.project, "rev-parse", "develop")
        self.success(self.run_workspace(task="local", base="refs/heads/develop"))
        self.assertEqual(self.git(self.project, "rev-parse", "feature/local"), local_commit)

    def test_remote_only_base_is_fetched_even_with_a_narrow_fetch_refspec(self):
        self.git(self.project, "push", "--quiet", "origin", "develop:refs/heads/release")
        self.git(self.project, "config", "remote.origin.fetch",
                 "+refs/heads/develop:refs/remotes/origin/develop")
        self.success(self.run_workspace(base="release"))
        self.assertEqual(self.upstream(), "")

    def test_same_name_upstream_works_with_a_narrow_fetch_refspec(self):
        self.git(self.project, "push", "--quiet", "origin", "develop:refs/heads/feature/sample")
        self.git(self.project, "config", "remote.origin.fetch",
                 "+refs/heads/develop:refs/remotes/origin/develop")
        data = self.success(self.run_workspace())
        self.assertEqual(data["workspaces"][0]["upstream"], "origin/feature/sample")
        self.assertEqual(self.upstream(), "refs/remotes/origin/feature/sample")
        self.assertEqual(self.git(self.project / ".worktrees/feature/sample", "rev-parse",
                                  "--abbrev-ref", "@{upstream}"), "origin/feature/sample")

    def test_conflicting_fetch_mappings_require_a_decision_before_creation(self):
        self.git(self.project, "push", "--quiet", "origin", "develop:refs/heads/feature/sample")
        for index, refspec in enumerate([
            "+refs/heads/*:refs/remotes/elsewhere/*",
            "^refs/heads/feature/*",
        ]):
            with self.subTest(refspec=refspec):
                project = self.new_project("mapping-{}".format(index))
                if refspec.startswith("^"):
                    self.git(project, "config", "--add", "remote.origin.fetch", refspec)
                else:
                    self.git(project, "config", "remote.origin.fetch", refspec)
                result = self.run_workspace(root=project)
                self.assertNotEqual(result.returncode, 0)
                self.assert_no_workspace(project)

    def test_creation_failure_reports_completed_and_incomplete_worktrees(self):
        second = self.new_project("second")
        hook = second / ".git/hooks/post-checkout"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        result = self.run_workspace(root=self.root)
        self.assertNotEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual([entry["project"] for entry in data["workspaces"]], [str(self.project)])
        self.assertEqual(data["failed_project"], str(second))
        self.assertIn("error", data)
        self.assertEqual(self.git(self.project / ".worktrees/feature/sample", "branch", "--show-current"),
                         "feature/sample")
        self.assertTrue((second / ".worktrees/feature/sample").exists())

    def test_local_only_base_is_supported(self):
        self.git(self.project, "branch", "local-base")
        self.success(self.run_workspace(base="local-base"))
        self.assertEqual(self.upstream(), "")

    def test_existing_branch_and_path_are_preserved_and_require_a_decision(self):
        self.git(self.project, "branch", "feature/sample")
        result = self.run_workspace()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.project / ".worktrees").exists())
        self.git(self.project, "branch", "-D", "feature/sample")
        target = self.project / ".worktrees/feature/sample"
        target.mkdir(parents=True)
        (target / "keep").write_text("preserve")
        result = self.run_workspace()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((target / "keep").read_text(), "preserve")

    def test_branch_namespace_collisions_fail_before_any_project_is_created(self):
        for index, conflicting in enumerate(["feature", "feature/sample/old"]):
            with self.subTest(conflicting=conflicting):
                first = self.new_project("namespace-{}/a".format(index))
                second = self.new_project("namespace-{}/b".format(index))
                self.git(second, "branch", conflicting)
                result = self.run_workspace(root=first.parent)
                self.assertNotEqual(result.returncode, 0)
                self.assert_no_workspace(first)
                self.assert_no_workspace(second)

    def test_existing_remote_with_different_history_requires_a_decision(self):
        self.git(self.project, "checkout", "--quiet", "-b", "remote-only")
        (self.project / "remote.txt").write_text("remote\n")
        self.git(self.project, "add", "remote.txt")
        self.git(self.project, "commit", "--quiet", "-m", "remote only")
        self.git(self.project, "push", "--quiet", "origin", "HEAD:refs/heads/feature/sample")
        self.git(self.project, "checkout", "--quiet", "develop")
        result = self.run_workspace()
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_workspace()

    def test_symlinked_worktree_parent_cannot_escape_the_project(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.project / ".worktrees").symlink_to(outside, target_is_directory=True)
        result = self.run_workspace()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])
        self.assert_no_workspace()

    def test_missing_base_inaccessible_origin_and_empty_task_fail(self):
        for kwargs in [{"base": "missing"}, {"task": ""}]:
            with self.subTest(kwargs=kwargs):
                self.assertNotEqual(self.run_workspace(**kwargs).returncode, 0)
                self.assert_no_workspace()
        self.git(self.project, "remote", "set-url", "origin", str(self.root / "missing.git"))
        result = self.run_workspace()
        self.assertNotEqual(result.returncode, 0)
        self.assert_no_workspace()


if __name__ == "__main__":
    unittest.main()
