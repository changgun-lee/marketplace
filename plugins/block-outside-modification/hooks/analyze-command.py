#!/usr/bin/env python3
"""정적으로 해석 가능한 Bash 명령의 수정 대상 검사. 실행/eval은 하지 않는다.

지원하지 않는 쉘 구문은 종료 코드 3으로 기존 Bash 검사에 위임한다.
Python 3.6 이상, 표준 라이브러리만 사용한다.
"""
import json
import os
import re
import shlex
import subprocess
import sys


class Unsupported(ValueError):
    pass


def absolute(path, cwd):
    # POSIX의 // 특수 표기를 별도 루트로 오인하지 않도록 통일한다.
    return '/' + os.path.normpath(os.path.join(cwd, path)).lstrip('/')


def within(path, root):
    return path == root or path.startswith(root.rstrip('/') + '/')


def git(directory, *args):
    # 훅을 시작한 프로세스의 GIT_DIR/GIT_WORK_TREE 등으로 저장소가 바뀌지 않게 한다.
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    try:
        return subprocess.check_output(
            ['git', '-C', directory] + list(args), env=env,
            stderr=subprocess.DEVNULL, timeout=3).decode('utf-8', 'surrogateescape')
    except (OSError, subprocess.SubprocessError):
        return None


def common_dir(directory):
    value = git(directory, 'rev-parse', '--git-common-dir')
    return os.path.realpath(os.path.join(directory, value.rstrip('\n'))) if value else None


class AllowedPaths:
    def __init__(self, project):
        self.roots = {absolute(project, os.getcwd()), os.path.realpath(project)}
        common = common_dir(project)
        listing = git(project, 'worktree', 'list', '--porcelain', '-z') if common else None
        top = git(project, 'rev-parse', '--show-toplevel') if common else None
        top = os.path.realpath(top.rstrip('\n')) if top else None
        if listing:
            for field in listing.split('\0'):
                if not field.startswith('worktree '):
                    continue
                path = field[len('worktree '):]
                # 프로젝트가 저장소 하위 디렉토리인 경우 원래 루트를 넓히지 않는다.
                if os.path.realpath(path) == top:
                    continue
                if os.path.isdir(path) and common_dir(path) == common:
                    self.roots.update((absolute(path, os.getcwd()), os.path.realpath(path)))
        self.physical_roots = {os.path.realpath(root) for root in self.roots}

    def contains(self, path):
        if path in {'/dev/null', '/dev/stdout', '/dev/stderr', '/dev/tty',
                    '/dev/zero', '/dev/random', '/dev/urandom', '/dev/stdin'}:
            return True
        if within(path, '/dev/fd') and path != '/dev/fd':
            return True
        if any(within(path, root) for root in self.roots):
            return True
        # 루트 자체의 별칭만 해석한다. 루트 아래의 링크를 따라가 기존 정책을
        # 뒤집지 않으며, 존재하지 않는 새 파일/디렉토리도 검사할 수 있다.
        parent = path
        while parent != '/':
            if os.path.realpath(parent) in self.physical_roots:
                return True
            parent = os.path.dirname(parent)
        return '/' in self.roots


# 따옴표 안의 연산자는 단어에 남긴다. shlex.split만 쓰면 >/path를 분리하지
# 못하고, punctuation_chars만 쓰면 인용된 ';'와 실제 연산자를 구별하지 못한다.
WORD = re.compile(r'''(?:\\[\s\S]|'[^']*'|"(?:\\[\s\S]|[^"\\])*"|[^\s;&|<>()'"\\])+''')
OPERATOR = re.compile(r'(?:[0-9]+)?(?:&>>|&>|>>|>\||>&|<>|>|<&|<)|&&|\|\||[;|&()\n]')
REDIRECT = re.compile(r'^[0-9]*(?:&>>|&>|>>|>\||>&|<>|>|<&|<)$')


def remove_continuations(command):
    """큰따옴표 안의 작은따옴표, 주석, 이스케이프를 구분한다."""
    result = []
    quote = None
    index = 0
    while index < len(command):
        char = command[index]
        if quote is None and char == '#' and (index == 0 or command[index - 1] in ' \t\n;&|()<>'):
            end = command.find('\n', index)
            if end < 0:
                result.append(command[index:])
                break
            result.append(command[index:end + 1])
            index = end + 1
            continue
        if char == '\\' and quote != "'" and index + 1 < len(command):
            pair = command[index:index + 2]
            if pair != '\\\n':
                result.append(pair)
            index += 2
            continue
        if char == quote:
            quote = None
        elif quote is None and char in "'\"":
            quote = char
        result.append(char)
        index += 1
    return ''.join(result)


def check_expansions(raw):
    quote = None
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == '\\' and quote != "'":
            index += 2
            continue
        if char == quote:
            quote = None
        elif quote is None and char in "'\"":
            quote = char
        elif (quote != "'" and char in '$`') or (quote is None and char in '*?[]{}'):
            raise Unsupported('쉘 확장')
        index += 1


def tokenize(command):
    command = remove_continuations(command)
    tokens = []
    index = 0
    while index < len(command):
        if command.startswith('\\\n', index):
            index += 2
            continue
        char = command[index]
        if char in ' \t\r':
            index += 1
            continue
        if char == '#':
            end = command.find('\n', index)
            index = len(command) if end < 0 else end
            continue
        operator = OPERATOR.match(command, index)
        if operator:
            tokens.append(('op', operator.group()))
            index = operator.end()
            continue
        word = WORD.match(command, index)
        if not word:
            raise Unsupported('닫히지 않은 따옴표 또는 미지원 구문')
        raw = word.group()
        check_expansions(raw)
        value = shlex.split(raw, comments=False, posix=True)[0]
        if raw.startswith('~'):
            if value == '~' or value.startswith('~/'):
                value = os.path.expanduser(value)
            else:
                raise Unsupported('사용자 홈 확장')
        tokens.append(('word', value))
        index = word.end()
    return tokens


def split_commands(tokens):
    commands = []
    words, writes = [], []
    index = 0
    while index < len(tokens):
        kind, value = tokens[index]
        if kind == 'word':
            words.append(value)
        elif REDIRECT.match(value):
            if index + 1 >= len(tokens) or tokens[index + 1][0] != 'word':
                raise Unsupported('리다이렉션')
            target = tokens[index + 1][1]
            op = value.lstrip('0123456789')
            if op in {'>', '>>', '>|', '&>', '&>>', '<>'}:
                writes.append(target)
            elif op == '>&' and not re.match(r'^(?:[0-9]+-?|-)$', target):
                writes.append(target)
            index += 1
        elif value in {';', '\n', '&&', '|'}:
            commands.append((words, writes, value))
            words, writes = [], []
        else:
            raise Unsupported('복합 쉘 구문')
        index += 1
    commands.append((words, writes, ''))
    return commands


def parse_options(args, value_options=()):
    """옵션 값과 묶인 짧은 옵션(-cr, -dm755)을 파일 인자와 구별한다."""
    files, options = [], {}
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == '--':
            return files + args[index + 1:], options
        if arg.startswith('--'):
            option, separator, value = arg.partition('=')
            if not separator and option in value_options:
                index += 1
                if index >= len(args):
                    raise Unsupported('옵션 값 없음')
                value = args[index]
            options[option] = value
        elif arg.startswith('-') and arg != '-':
            for position in range(1, len(arg)):
                option = '-' + arg[position]
                options[option] = ''
                if option in value_options:
                    value = arg[position + 1:]
                    if not value:
                        index += 1
                        if index >= len(args):
                            raise Unsupported('옵션 값 없음')
                        value = args[index]
                    options[option] = value
                    break
        else:
            files.append(arg)
        index += 1
    return files, options


def operands(args, value_options=()):
    return parse_options(args, value_options)[0]


def copy_targets(name, args):
    files, options = parse_options(args, {'-t', '--target-directory', '-S', '--suffix',
                                         '-m', '--mode', '-o', '--owner', '-g', '--group'})
    target = options.get('-t', options.get('--target-directory'))
    if name == 'mv':
        return files + ([target] if target else [])
    if name == 'install' and ('-d' in options or '--directory' in options):
        return files
    if target is not None:
        return [target]
    # cp/ln/install의 마지막 인자가 목적지. ln SOURCE는 현재 디렉토리에 생성.
    return files[-1:] if len(files) > 1 else (['.'] if name == 'ln' and files else [])


def sed_targets(args):
    inplace = False
    script_seen = False
    files = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == '--':
            rest = args[index + 1:]
            files.extend(rest if script_seen else rest[1:])
            break
        if arg in {'-e', '-f', '--expression', '--file'}:
            script_seen = True
            index += 2
            continue
        if arg.startswith(('--expression=', '--file=', '-e', '-f')):
            script_seen = True
        elif arg.startswith('--in-place') or re.match(r'^-[a-zA-Z]*i', arg):
            inplace = True
            # BSD sed -i ''와 GNU sed -i를 함께 처리한다.
            if arg == '-i' and index + 1 < len(args) and args[index + 1] == '':
                index += 1
        elif arg.startswith('-'):
            pass
        elif not script_seen:
            script_seen = True
        else:
            files.append(arg)
        index += 1
    return files if inplace else []


def modification_targets(name, args):
    if name in {'cp', 'mv', 'ln', 'install'}:
        return copy_targets(name, args)
    if name == 'sed':
        return sed_targets(args)
    if name == 'dd':
        return [a[3:] for a in args if a.startswith('of=')]
    if name in {'chmod', 'chown', 'chgrp'}:
        if name == 'chmod':
            # -w/-rw 같은 모드는 옵션이 아니다. 첫 파일을 모드로 버리지 않는다.
            args = ['MODE' if re.match(r'^-[rwxXstugo,+=-]+$', a) else a for a in args]
        files = operands(args, {'--reference'})
        reference = any(a == '--reference' or a.startswith('--reference=') for a in args)
        return files if reference else files[1:]
    if name in {'rm', 'rmdir', 'unlink', 'tee', 'touch', 'mkdir', 'truncate'}:
        options = {'-d', '-t', '-r', '--date', '--reference', '--time'} if name == 'touch' else set()
        if name == 'mkdir':
            options = {'-m', '--mode'}
        if name == 'truncate':
            options = {'-s', '--size', '-r', '--reference'}
        return operands(args, options)
    if name in {'patch', 'eval', 'source', '.', 'bash', 'sh', 'zsh', 'sudo', 'env',
                'xargs', 'find', 'if', 'for', 'while', 'until', 'case', 'function',
                'pushd', 'popd', 'exec', 'command'}:
        raise Unsupported('명령별 정적 분석 미지원')
    # 알 수 없는 명령에 기존 수정 키워드가 있으면 기존 검사를 적용한다.
    if any(re.search(r'\b(rm|rmdir|mv|cp|tee|truncate|chmod|chown|chgrp|touch|mkdir|ln|install|patch|dd|unlink|sed)\b|>', a)
           for a in [name] + args) and name not in {'echo', 'printf'}:
        raise Unsupported('수정 가능성이 있는 명령')
    return []


def analyze(command, cwd):
    writes = []
    previous = ''
    current_dirs = {cwd}
    skipped_dirs = set()
    for words, redirects, following in split_commands(tokenize(command)):
        if not words:
            writes.extend(absolute(path, directory) for directory in current_dirs for path in redirects)
            # && 뒤 줄바꿈은 조건 연결을 종료하지 않는다.
            if not redirects and following == '\n' and previous in {'&&', '|'}:
                continue
            if following not in {'&&', '|'}:
                current_dirs.update(skipped_dirs)
                skipped_dirs.clear()
            previous = following
            continue
        if re.match(r'^[A-Za-z_][A-Za-z_0-9]*=', words[0]):
            raise Unsupported('명령 앞 환경변수 할당')
        name = os.path.basename(words[0])
        args = words[1:]
        writes.extend(absolute(path, directory) for directory in current_dirs for path in redirects)
        success_dirs = set(current_dirs)
        failure_dirs = set(current_dirs)
        if name == 'cd':
            if previous == '|' or following == '|':
                raise Unsupported('파이프 안의 cd')
            paths = operands(args)
            if len(paths) > 1 or paths == ['-']:
                raise Unsupported('cd 인자')
            target = paths[0] if paths else os.path.expanduser('~')
            if os.environ.get('CDPATH') and not os.path.isabs(target):
                raise Unsupported('CDPATH')
            success_dirs = set()
            failure_dirs = set()
            for directory in current_dirs:
                new_cwd = absolute(target, directory)
                if '-P' in args:
                    new_cwd = os.path.realpath(new_cwd)
                if os.path.isdir(new_cwd) and os.access(new_cwd, os.X_OK):
                    success_dirs.add(new_cwd)
                else:
                    failure_dirs.add(directory)
        else:
            targets = modification_targets(name, args)
            # tee/sed의 '-'는 표준 입출력이다. dd of=-는 실제 파일 이름이다.
            writes.extend(absolute(path, directory) for directory in current_dirs for path in targets
                          if path != '-' or name not in {'tee', 'sed'})
            if name in {'true', ':'} and not redirects:
                failure_dirs.clear()
            elif name == 'false':
                success_dirs.clear()
        if following == '&&':
            skipped_dirs.update(failure_dirs)
            current_dirs = success_dirs
        elif following == '|':
            # 파이프의 각 명령은 같은 cwd에서 시작한다. 파이프 안 cd는 위에서 제외.
            pass
        else:
            # 조건 때문에 cd가 생략된 경로도 다음 명령의 cwd 후보로 보존한다.
            current_dirs = success_dirs | failure_dirs | skipped_dirs
            skipped_dirs.clear()
        previous = following
    return writes


def main():
    data = json.load(sys.stdin)
    if data.get('tool_name') != 'Bash':
        return
    command = data.get('tool_input', {}).get('command', '')
    if not command:
        return
    cwd = absolute(data.get('cwd') or os.getcwd(), os.getcwd())
    project = os.environ.get('CLAUDE_PROJECT_DIR') or cwd
    # 기존 동작: 기준 디렉토리를 확인할 수 없으면 검사하지 않는다.
    if not os.path.isdir(project):
        return
    writes = analyze(command, cwd)
    if not writes:
        return
    allowed = AllowedPaths(project)
    outside = sorted({path for path in writes if not allowed.contains(path)})
    if outside:
        reason = ('프로젝트 디렉토리 외부 파일을 수정/삭제하는 Bash 명령이 감지되어 실행을 차단했습니다.\n\n'
                  '허용 프로젝트/worktree 경로:\n{}\n\n현재 작업 경로: {}\n\n명령:\n{}\n\n'
                  '프로젝트 외부 수정 대상:\n{}\n\n'
                  '실행이 꼭 필요한 경우 사용자에게 확인을 받은 뒤 사용자가 직접 실행하도록 안내해주세요.'
                  ).format('\n'.join(sorted(allowed.roots)), cwd, command, '\n'.join(outside))
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                         'permissionDecision': 'deny', 'permissionDecisionReason': reason}}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (Unsupported, ValueError, OSError):
        sys.exit(3)
