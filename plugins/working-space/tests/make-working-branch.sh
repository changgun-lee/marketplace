#!/bin/bash

set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
script="$script_dir/../scripts/make-working-branch.sh"
temp_dir=$(mktemp -d)
trap 'rm -rf "$temp_dir"' EXIT

project_name="sample-project"
origin_dir="$temp_dir/remotes/$project_name.git"
project_dir="$temp_dir/workspace/$project_name"

mkdir -p "$temp_dir/remotes" "$temp_dir/workspace"
git init --bare --quiet "$origin_dir"
git init --quiet -b production "$temp_dir/seed"
git -C "$temp_dir/seed" config user.name "Test User"
git -C "$temp_dir/seed" config user.email "test@example.com"
printf 'production\n' > "$temp_dir/seed/README.md"
git -C "$temp_dir/seed" add README.md
git -C "$temp_dir/seed" commit --quiet -m "Seed production"
git -C "$temp_dir/seed" remote add origin "$origin_dir"
git -C "$temp_dir/seed" push --quiet origin production
git clone --quiet --branch production "$origin_dir" "$project_dir"

cat > "$temp_dir/gitconfig" <<EOF
[url "file://$temp_dir/remotes/"]
    insteadOf = https://github.com/changgun-lee/
[url "file://$temp_dir/missing/"]
    insteadOf = https://github.com/team-commdev/
EOF

if ! (cd "$temp_dir/workspace" && GIT_CONFIG_GLOBAL="$temp_dir/gitconfig" GIT_CONFIG_NOSYSTEM=1 bash "$script" "new feature") > "$temp_dir/output" 2>&1; then
    cat "$temp_dir/output"
    exit 1
fi

branch="feature/new-feature"
if ! git -C "$project_dir" show-ref --verify --quiet "refs/heads/$branch"; then
    cat "$temp_dir/output"
    echo "Expected local branch $branch to be created" >&2
    exit 1
fi
production_commit=$(git -C "$temp_dir/seed" rev-parse production)
branch_commit=$(git -C "$project_dir" rev-parse "$branch")
remote_commit=$(git --git-dir="$origin_dir" rev-parse "refs/heads/$branch")
tracking_branch=$(git -C "$project_dir" rev-parse --abbrev-ref --symbolic-full-name "$branch@{upstream}")
current_branch=$(git -C "$project_dir" branch --show-current)
remotes=$(git -C "$project_dir" remote)

test "$branch_commit" = "$production_commit"
test "$remote_commit" = "$production_commit"
test "$tracking_branch" = "origin/$branch"
test "$current_branch" = "$branch"
test "$remotes" = "origin"

cat > "$temp_dir/missing-gitconfig" <<EOF
[url "file://$temp_dir/missing/"]
    insteadOf = https://github.com/changgun-lee/
EOF

if (cd "$temp_dir/workspace" && GIT_CONFIG_GLOBAL="$temp_dir/missing-gitconfig" GIT_CONFIG_NOSYSTEM=1 bash "$script" "new feature") > "$temp_dir/error-output" 2>&1; then
    cat "$temp_dir/error-output"
    echo "Expected an inaccessible origin to fail" >&2
    exit 1
fi

grep -q "ERROR: Cannot access origin repository" "$temp_dir/error-output"
if grep -q "All projects processed successfully" "$temp_dir/error-output"; then
    cat "$temp_dir/error-output"
    echo "An origin failure must not be reported as success" >&2
    exit 1
fi

echo "make-working-branch: origin-only creation and origin failure passed"
