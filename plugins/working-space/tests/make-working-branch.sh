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
original_origin_url=$(git -C "$project_dir" config --get remote.origin.url)

cat > "$temp_dir/gitconfig" <<EOF
[url "file://$temp_dir/remotes/"]
    insteadOf = https://github.com/changgun-lee/
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
current_origin_url=$(git -C "$project_dir" config --get remote.origin.url)

test "$branch_commit" = "$production_commit"
test "$remote_commit" = "$production_commit"
test "$tracking_branch" = "origin/$branch"
test "$current_branch" = "$branch"
test "$remotes" = "origin"
if [ "$current_origin_url" != "$original_origin_url" ]; then
    echo "Expected origin URL to stay $original_origin_url, got $current_origin_url" >&2
    exit 1
fi

git -C "$project_dir" remote set-url origin "$temp_dir/missing/$project_name.git"

if (cd "$temp_dir/workspace" && GIT_CONFIG_GLOBAL="$temp_dir/gitconfig" GIT_CONFIG_NOSYSTEM=1 bash "$script" "new feature") > "$temp_dir/error-output" 2>&1; then
    cat "$temp_dir/error-output"
    echo "Expected an inaccessible origin to fail" >&2
    exit 1
fi

grep -q "ERROR: Cannot access origin repository" "$temp_dir/error-output"
test "$(git -C "$project_dir" config --get remote.origin.url)" = "$temp_dir/missing/$project_name.git"
if grep -q "All projects processed successfully" "$temp_dir/error-output"; then
    cat "$temp_dir/error-output"
    echo "An origin failure must not be reported as success" >&2
    exit 1
fi

git -C "$project_dir" remote remove origin
if (cd "$temp_dir/workspace" && GIT_CONFIG_GLOBAL="$temp_dir/gitconfig" GIT_CONFIG_NOSYSTEM=1 bash "$script" "new feature") > "$temp_dir/missing-origin-output" 2>&1; then
    cat "$temp_dir/missing-origin-output"
    echo "Expected a missing origin to fail" >&2
    exit 1
fi

grep -q "ERROR: origin remote is not configured" "$temp_dir/missing-origin-output"
test -z "$(git -C "$project_dir" remote)"

echo "make-working-branch: origin URL preserved and origin errors handled"
