#!/usr/bin/env python3
"""Create project-local Git worktrees without inheriting the base's upstream."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


class WorkspaceError(Exception):
    pass


def git(project, *args, **kwargs):
    result = subprocess.run(
        ["git", "-C", str(project), *args], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, encoding="utf-8", errors="surrogateescape",
        env=dict(os.environ, GIT_TERMINAL_PROMPT="0"),
    )
    if result.returncode and kwargs.get("check", True):
        raise WorkspaceError("{}: {}".format(project, result.stderr.strip() or "Git 명령 실패"))
    return result


def branch_name(task):
    if not task:
        raise WorkspaceError("작업명이 비어 있습니다. 작업명을 지정하세요.")
    suffix = "".join(
        "-" if ord(char) < 32 or ord(char) == 127
        or char in " ~^:?*[\\/" else char for char in task
    )
    suffix = re.sub(r"\.{2,}", lambda match: "-" * len(match.group()), suffix)
    suffix = suffix.replace("@{", "@-")
    if suffix.startswith("."):
        suffix = "-" + suffix[1:]
    if suffix.endswith("."):
        suffix = suffix[:-1] + "-"
    if suffix.endswith(".lock"):
        suffix = suffix[:-5] + "-lock"
    return "feature/" + suffix


def within(path, root):
    return os.path.commonpath([str(path), str(root)]) == str(root)


def without_final_lf(value):
    # Unicode whitespace/separators are valid inside Git refs and filesystem paths.
    return value[:-1] if value.endswith("\n") else value


def project_root(path):
    if not (path / ".git").exists():
        raise WorkspaceError("{}: Git 프로젝트 루트가 아닙니다.".format(path))
    actual = Path(without_final_lf(git(path, "rev-parse", "--show-toplevel").stdout)).resolve()
    if actual != path:
        raise WorkspaceError("{}: Git 프로젝트 루트를 확인하세요.".format(path))
    return path


def discover(root, selected):
    if selected:
        projects = []
        for value in selected:
            path = (root / value).resolve()
            if not within(path, root):
                raise WorkspaceError("탐색 범위 밖의 프로젝트입니다: {}".format(path))
            projects.append(project_root(path))
    else:
        projects = []

        def walk_error(error):
            raise WorkspaceError("프로젝트 탐색 실패: {}".format(error))

        for current, dirs, files in os.walk(str(root), onerror=walk_error, followlinks=False):
            if ".git" in dirs or ".git" in files:
                projects.append(project_root(Path(current).resolve()))
            dirs[:] = sorted(name for name in dirs if name not in {".git", ".worktrees"}
                             and not (Path(current) / name).is_symlink())
    projects = sorted(set(projects))
    if not projects:
        raise WorkspaceError("{}: 현재 또는 하위에 Git 프로젝트가 없습니다.".format(root))
    common_dirs = set()
    for project in projects:
        common = Path(without_final_lf(git(project, "rev-parse", "--git-common-dir").stdout))
        common = (project / common).resolve()
        if common in common_dirs:
            raise WorkspaceError("같은 저장소의 checkout이 여러 개입니다. --project로 대상을 지정하세요.")
        common_dirs.add(common)
    return projects


def parse_base(project, base):
    if base.startswith("refs/heads/"):
        mode, name = "local", base[len("refs/heads/"):]
    elif base.startswith("refs/remotes/origin/"):
        mode, name = "remote", base[len("refs/remotes/origin/"):]
    elif base.startswith("origin/"):
        mode, name = "remote", base[len("origin/"):]
    elif base.startswith("refs/"):
        raise WorkspaceError("기반은 로컬 브랜치 또는 origin 브랜치로 지정하세요.")
    else:
        mode, name = "remote", base
    if not name or name.startswith("-") or git(
        project, "check-ref-format", "refs/heads/" + name, check=False
    ).returncode:
        raise WorkspaceError("유효하지 않은 기반 브랜치입니다: {}".format(base))
    return mode, name


def remote_heads(project, names):
    if git(project, "remote", "get-url", "origin", check=False).returncode:
        raise WorkspaceError("{}: origin 원격이 없습니다. 사용할 원격을 확인하세요.".format(project))
    refs = ["refs/heads/" + name for name in sorted(set(names))]
    result = git(project, "ls-remote", "--heads", "--", "origin", *refs)
    heads = {}
    for line in result.stdout.split("\n"):
        if not line:
            continue
        oid, ref = line.split("\t", 1)
        if ref in refs:
            heads[ref[len("refs/heads/"):]] = oid
    return heads


def check_target(project, branch):
    target = project / ".worktrees" / branch
    for path in [project / ".worktrees", target.parent, target]:
        if path.is_symlink():
            raise WorkspaceError("{}: 워크트리 경로의 심볼릭 링크를 사용할 수 없습니다.".format(path))
        if path != target and path.exists() and not path.is_dir():
            raise WorkspaceError("{}: 워크트리 상위 경로가 디렉토리가 아닙니다.".format(path))
    if not within(target.resolve(), project):
        raise WorkspaceError("워크트리 경로가 프로젝트 밖입니다: {}".format(target))
    if target.exists():
        raise WorkspaceError("{}: 경로가 이미 있습니다. 재사용 여부 또는 새 작업명을 결정하세요.".format(target))
    wanted = "refs/heads/" + branch
    for ref in git(project, "for-each-ref", "--format=%(refname)", "refs/heads/").stdout.split("\n"):
        if ref == wanted or ref.startswith(wanted + "/") or wanted.startswith(ref + "/"):
            raise WorkspaceError("{}: {}와 충돌하는 브랜치 {}가 있습니다. "
                                 "재사용 여부 또는 새 작업명을 결정하세요.".format(project, branch, ref))
    for key in ("remote", "merge"):
        if git(project, "config", "--get-all", "branch.{}.{}".format(branch, key),
               check=False).returncode == 0:
            raise WorkspaceError("{}: {}의 기존 추적 설정을 먼저 확인하세요.".format(project, branch))
    registered = git(project, "worktree", "list", "--porcelain", "-z").stdout.split("\0")
    if "worktree " + str(target) in registered:
        raise WorkspaceError("{}: 이미 등록된 워크트리 경로입니다. 정리 또는 재사용을 결정하세요.".format(target))
    if git(project, "ls-files", "-z", "--", ".worktrees").stdout:
        raise WorkspaceError("{}: .worktrees 안에 추적 중인 파일이 있습니다.".format(project))
    return target


def refspec_match(pattern, ref):
    if "*" not in pattern:
        return "" if pattern == ref else None
    prefix, suffix = pattern.split("*", 1)
    if ref.startswith(prefix) and ref.endswith(suffix) and len(ref) >= len(prefix) + len(suffix):
        return ref[len(prefix):len(ref) - len(suffix)] if suffix else ref[len(prefix):]
    return None


def tracking_refspec(project, branch):
    source = "refs/heads/" + branch
    target = "refs/remotes/origin/" + branch
    mapped = False
    specs = git(project, "config", "--get-all", "remote.origin.fetch", check=False).stdout.split("\n")
    for spec in specs:
        if spec.startswith("^"):
            conflict = refspec_match(spec[1:], source) is not None
        elif ":" in spec:
            left, right = spec.lstrip("+").split(":", 1)
            match = refspec_match(left, source)
            inverse = refspec_match(right, target)
            destination = right.replace("*", match) if match is not None else None
            origin = left.replace("*", inverse) if inverse is not None else None
            conflict = ((destination is not None and destination != target)
                        or (origin is not None and origin != source))
            mapped = mapped or destination == target
        else:
            continue
        if conflict:
            raise WorkspaceError("{}: origin의 fetch 설정 {}가 동명 브랜치 추적과 충돌합니다. "
                                 "설정 변경 여부를 결정하세요.".format(project, spec))
    return None if mapped else "+{}:{}".format(source, target)


def plan_project(project, base, branch):
    git(project, "check-ref-format", "--branch", branch)
    target = check_target(project, branch)
    mode, name = parse_base(project, base)
    heads = remote_heads(project, [name, branch])
    local_ref = "refs/heads/" + name
    local = git(project, "rev-parse", "--verify", local_ref + "^{commit}", check=False)
    local_oid = without_final_lf(local.stdout) if local.returncode == 0 else None
    remote_oid = heads.get(name)
    use_remote = mode == "remote"
    oid = remote_oid if use_remote else local_oid
    if oid is None:
        raise WorkspaceError("{}: 기반 브랜치 {}가 없습니다.".format(project, base))
    if branch in heads and heads[branch] != oid:
        raise WorkspaceError(
            "{}: origin/{}가 기반과 다른 커밋에 있습니다. "
            "기존 원격 작업을 이어갈지 새 작업명을 쓸지 결정하세요.".format(project, branch)
        )
    fetch = {}
    if use_remote:
        fetch[name] = oid
    if branch in heads:
        fetch[branch] = heads[branch]
    return {
        "project": str(project), "worktree": str(target),
        "base_ref": "refs/remotes/origin/" + name if use_remote else local_ref,
        "base_commit": oid, "upstream": "origin/" + branch if branch in heads else None,
        "tracking_refspec": tracking_refspec(project, branch) if branch in heads else None,
        "fetch": fetch,
    }


def fetch_project(plan):
    project = Path(plan["project"])
    if not plan["fetch"]:
        return
    refspecs = ["+refs/heads/{0}:refs/remotes/origin/{0}".format(name)
                for name in sorted(plan["fetch"])]
    git(project, "fetch", "--no-tags", "--", "origin", *refspecs)
    for name, oid in plan["fetch"].items():
        current = without_final_lf(git(project, "rev-parse", "--verify", "refs/remotes/origin/" + name).stdout)
        if current != oid:
            raise WorkspaceError("{}: 원격 브랜치가 검사 중 변경됐습니다. 다시 확인하세요.".format(project))


def ignore_worktrees(project):
    if git(project, "check-ignore", "--quiet", "--", ".worktrees/", check=False).returncode == 0:
        return
    exclude = Path(without_final_lf(git(project, "rev-parse", "--git-path", "info/exclude").stdout))
    exclude = project / exclude
    if exclude.is_symlink():
        raise WorkspaceError("{}: 심볼릭 링크인 exclude 파일을 수정하지 않습니다.".format(exclude))
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open("a", encoding="utf-8") as stream:
        stream.write("\n# gpt-workspace: local worktrees\n/.worktrees/\n")
    if git(project, "check-ignore", "--quiet", "--", ".worktrees/", check=False).returncode:
        raise WorkspaceError("{}: .worktrees 제외 설정을 확인하세요.".format(project))


def create_workspace(plan, branch):
    project = Path(plan["project"])
    target = check_target(project, branch)
    ignore_worktrees(project)
    if plan["tracking_refspec"]:
        # Single-branch clones need this exact mapping for Git to resolve @{upstream}.
        git(project, "config", "--local", "--add", "remote.origin.fetch", plan["tracking_refspec"])
    target.parent.mkdir(parents=True, exist_ok=True)
    # Both --no-track and a commit ID avoid inheriting even branch.autoSetupMerge=always/inherit.
    git(project, "worktree", "add", "--no-track", "-b", branch, "--", str(target), plan["base_commit"])
    if plan["upstream"]:
        git(project, "branch", "--set-upstream-to=refs/remotes/" + plan["upstream"], branch)
    actual = without_final_lf(git(project, "for-each-ref", "--format=%(upstream)", "refs/heads/" + branch).stdout)
    expected = "refs/remotes/" + plan["upstream"] if plan["upstream"] else ""
    if actual != expected:
        raise WorkspaceError("{}: upstream 검증 실패: {}".format(project, actual))
    if without_final_lf(git(target, "symbolic-ref", "HEAD").stdout) != "refs/heads/" + branch:
        raise WorkspaceError("{}: 작업 브랜치 검증에 실패했습니다.".format(target))


def public_plan(plan):
    return {key: value for key, value in plan.items() if key != "fetch"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="탐색 시작 경로: 현재 프로젝트 또는 프로젝트들의 상위 폴더")
    parser.add_argument("--project", action="append", help="대상을 정확히 지정 (반복 가능, root 기준 경로)")
    parser.add_argument("--base", required=True,
                        help="기반 브랜치: xxx는 origin/xxx로 해석, 로컬은 refs/heads/xxx")
    parser.add_argument("--task", required=True, help="작업명 (feature/ 접두사는 자동 추가)")
    parser.add_argument("--dry-run", action="store_true", help="원격 조회와 사전 검사만 실행")
    args = parser.parse_args()
    output = {"workspaces": [], "dry_run": args.dry_run}
    current = None
    try:
        root = Path(args.root).resolve()
        if not root.is_dir():
            raise WorkspaceError("탐색 경로가 디렉토리가 아닙니다: {}".format(root))
        branch = branch_name(args.task)
        output["branch"] = branch
        plans = [plan_project(project, args.base, branch)
                 for project in discover(root, args.project)]
        if args.dry_run:
            output["workspaces"] = [public_plan(plan) for plan in plans]
        else:
            # Check/fetch every repository before creating any branch or worktree.
            for plan in plans:
                fetch_project(plan)
            for plan in plans:
                current = plan["project"]
                create_workspace(plan, branch)
                output["workspaces"].append(public_plan(plan))
    except (WorkspaceError, OSError, ValueError) as error:
        output["error"] = str(error)
        if current:
            output["failed_project"] = current
            output["recovery"] = "브랜치나 워크트리가 일부 생성됐을 수 있습니다. git worktree list와 git branch로 확인하고, 삭제하지 말고 보고하세요."
        print(json.dumps(output, ensure_ascii=True, indent=4))
        return 1
    print(json.dumps(output, ensure_ascii=True, indent=4))
    return 0


if __name__ == "__main__":
    sys.exit(main())
