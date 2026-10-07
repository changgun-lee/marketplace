"""실제 훅과 임시 Git 저장소를 검사한다. 검사 대상 명령은 실행하지 않는다."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

HOOK = Path(__file__).resolve().parents[1] / 'hooks/block-outside-modification.sh'


class HookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='outside-hook-')
        cls.base = Path(cls.temp.name).resolve()
        cls.project = cls.base / 'project space'
        cls.project.mkdir()
        cls.outside = cls.base / 'outside'
        cls.outside.mkdir()
        cls.alias = cls.base / 'alias'
        cls.alias.symlink_to(cls.project, target_is_directory=True)
        (cls.project / 'linked').symlink_to(cls.outside, target_is_directory=True)
        (cls.project / 'sub').mkdir()
        cls.git('init', str(cls.project))
        cls.git('-C', str(cls.project), '-c', 'user.name=Test', '-c',
                'user.email=test@example.invalid', 'commit', '--allow-empty', '-m', 'initial')
        cls.worktree = cls.base / 'worktree space'
        cls.git('-C', str(cls.project), 'worktree', 'add', '--detach', str(cls.worktree))
        (cls.worktree / 'sub').mkdir()
        cls.other = cls.base / 'other'
        cls.git('clone', '--local', str(cls.project), str(cls.other))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @staticmethod
    def git(*args):
        subprocess.check_output(['git'] + list(args), stderr=subprocess.STDOUT)

    def check(self, command, blocked=False, cwd=None, root=None, tool='Bash', extra_env=None):
        env = os.environ.copy()
        env['CLAUDE_PROJECT_DIR'] = str(root or self.project)
        if extra_env:
            env.update(extra_env)
        result = subprocess.run(
            ['bash', str(HOOK)], cwd=str(self.project), env=env,
            input=json.dumps({'tool_name': tool, 'cwd': str(cwd or self.project),
                              'tool_input': {'command': command}}),
            universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        output = json.loads(result.stdout) if result.stdout.strip() else {}
        decision = output.get('hookSpecificOutput', {}).get('permissionDecision')
        self.assertEqual(decision == 'deny' or output.get('decision') == 'block', blocked,
                         '{}\n{}'.format(command, result.stdout))
        return output

    def test_absolute_internal_and_external(self):
        self.check('touch ' + shlex.quote(str(self.project / 'new.txt')))
        self.check('touch ' + shlex.quote(str(self.outside / 'new.txt')), True)

    def test_root_alias_both_directions(self):
        self.check('touch ' + shlex.quote(str(self.project / 'new.txt')), root=self.alias)
        self.check('touch ' + shlex.quote(str(self.alias / 'new.txt')))

    def test_internal_symlink_policy_is_preserved(self):
        self.check('touch linked/new.txt')
        self.check('touch ' + shlex.quote(str(self.project / 'linked/new.txt')))

    def test_registered_worktree_absolute_and_relative(self):
        self.check('touch ' + shlex.quote(str(self.worktree / 'new.txt')))
        self.check('touch new.txt', cwd=self.worktree)
        self.check('touch ../new.txt', cwd=self.worktree / 'sub')

    def test_clone_is_not_same_worktree(self):
        self.check('touch new.txt', True, cwd=self.other)
        self.check('touch ' + shlex.quote(str(self.other / 'new.txt')), True)

    def test_external_cwd_does_not_expand_allowlist(self):
        self.check('touch new.txt', True, cwd=self.outside)
        self.check('touch ' + shlex.quote(str(self.project / 'new.txt')), cwd=self.outside)

    def test_relative_parent_escape(self):
        self.check('touch ../outside/new.txt', True)
        self.check('touch ../../outside/new.txt', True, cwd=self.project / 'sub')

    def test_absolute_executable_is_not_write_target(self):
        self.check('/usr/bin/touch ' + shlex.quote(str(self.project / 'new.txt')))
        self.check('/bin/rm ' + shlex.quote(str(self.outside / 'new.txt')), True)

    def test_copy_reads_source_but_move_modifies_source(self):
        source = shlex.quote(str(self.outside / 'input.txt'))
        self.check('cp {} new.txt'.format(source))
        self.check('mv {} new.txt'.format(source), True)
        self.check('cp new.txt {}'.format(source), True)
        self.check('cp -t {} new.txt'.format(shlex.quote(str(self.outside))), True)
        self.check('cp -t . {}'.format(source))

    def test_redirect_with_or_without_spaces(self):
        target = shlex.quote(str(self.outside / 'new.txt'))
        for op in ('>', '>>', '2>', '&>', '>|'):
            for space in ('', ' '):
                with self.subTest(op=op, space=space):
                    self.check('echo x {}{}{}'.format(op, space, target), True)
        self.check('cat {} >new.txt'.format(target))
        self.check('cat {} 2>/dev/null'.format(target))
        self.check('cat {} 2>&1'.format(target))

    def test_cd_tracks_working_directory_not_allowed_roots(self):
        external = shlex.quote(str(self.outside))
        self.check('cd {} && touch new.txt'.format(external), True)
        self.check('cd {}\ntouch new.txt'.format(external), True)
        self.check('cd sub && touch ../new.txt')
        self.check('cd {} && touch new.txt'.format(shlex.quote(str(self.worktree))))
        self.check('cd {} && cat input.txt; touch new.txt'.format(external), True)

    def test_read_command_and_quoted_text_are_not_targets(self):
        target = shlex.quote(str(self.outside / 'input.txt'))
        self.check('cat {} && touch new.txt'.format(target))
        self.check('echo "rm {} >"'.format(self.outside))
        self.check('touch new.txt # /outside/comment')
        self.check("touch 'semi;colon.txt' 'greater>than.txt'")

    def test_tee_and_sed(self):
        target = shlex.quote(str(self.outside / 'input.txt'))
        self.check('echo x | tee {}'.format(target), True)
        self.check('sed -n p {}'.format(target))
        self.check("sed -i '' 's/a/b/' {}".format(target), True)
        self.check("sed -i.bak 's/a/b/' new.txt")
        self.check("sed -i -e 's|/outside/a|b|' new.txt")

    def test_prefix_boundary_and_nonexistent_targets(self):
        self.check('mkdir -p new/nested/directory')
        self.check('touch ' + shlex.quote(str(self.project) + '-other/new.txt'), True)

    def test_git_environment_cannot_redirect_worktree_discovery(self):
        self.check('touch new.txt', True, cwd=self.other,
                   extra_env={'GIT_DIR': str(self.other / '.git'),
                              'GIT_WORK_TREE': str(self.other)})

    def test_non_bash_ignored(self):
        self.check('touch /outside/new.txt', tool='Read')

    def test_modes_and_combined_options(self):
        target = shlex.quote(str(self.outside / 'new.txt'))
        self.check('chmod -w ' + target, True)
        self.check('mkdir -Z ' + target, True)
        self.check('cp -at {} new.txt'.format(shlex.quote(str(self.outside))), True)
        self.check('cp -at . ' + target)

    def test_dd_output_and_dash_filename(self):
        self.check('dd if={} of=new.txt'.format(shlex.quote(str(self.outside / 'input.txt'))))
        self.check('dd if=new.txt of={}'.format(shlex.quote(str(self.outside / 'output.txt'))), True)
        self.check('dd of=-', True, cwd=self.outside)

    def test_non_git_project_and_subdirectory_root(self):
        self.check('touch new.txt', cwd=self.outside, root=self.outside)
        self.check('touch ../new.txt', True, cwd=self.project / 'sub', root=self.project / 'sub')
        self.check('touch new.txt', cwd=self.project, root=self.worktree)

    def test_fallback_still_checks_complex_commands(self):
        self.check('( touch {} )'.format(shlex.quote(str(self.outside / 'new.txt'))), True)
        self.check('patch ' + shlex.quote(str(self.outside / 'new.txt')), True)

    def test_new_output_uses_pretooluse_contract(self):
        result = self.check('touch ../outside/new.txt', True)
        self.assertEqual(result['hookSpecificOutput']['hookEventName'], 'PreToolUse')
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertIn(str(self.outside), result['hookSpecificOutput']['permissionDecisionReason'])

    def test_conditional_cd_does_not_change_skipped_branch(self):
        project = shlex.quote(str(self.project))
        external = shlex.quote(str(self.outside))
        self.check('false && cd {}; touch new.txt'.format(project), True, cwd=self.outside)
        self.check('false && cd {}; touch new.txt'.format(external))
        self.check('true && cd {}; touch new.txt'.format(project), cwd=self.outside)
        self.check('some-check && cd {}; touch new.txt'.format(project), True, cwd=self.outside)

    def test_line_continuation_in_executable(self):
        self.check('to\\\nuch ' + shlex.quote(str(self.outside / 'new.txt')), True)
        self.check('touch new\\\nfile.txt')
        self.check("touch 'new\\\nfile.txt'")

    def test_skipped_redirect_only_command(self):
        self.check('false && > marker; touch ' + shlex.quote(str(self.outside / 'new.txt')), True)

    def test_combined_install_and_touch_options(self):
        target = shlex.quote(str(self.outside / 'new.txt'))
        self.check('install -dm755 {} newdir'.format(target), True)
        self.check('touch -cr {} new.txt'.format(target))

    def test_apostrophes_in_double_quotes_do_not_hide_continuation(self):
        self.check('echo "don\'t"; to\\\nuch {}; echo "it\'s done"'.format(
            shlex.quote(str(self.outside / 'new.txt'))), True)

    def test_python_unavailable_keeps_legacy_fallback(self):
        with tempfile.TemporaryDirectory(prefix='hook-tools-') as temp:
            for name in ('bash', 'cat', 'jq', 'sed', 'tr', 'grep', 'awk'):
                Path(temp, name).symlink_to(shutil.which(name))
            self.check('touch ' + shlex.quote(str(self.outside / 'new.txt')), True,
                       extra_env={'PATH': temp})
            self.check('touch ' + shlex.quote(str(self.alias / 'new.txt')),
                       root=self.alias, extra_env={'PATH': temp})


if __name__ == '__main__':
    unittest.main()
