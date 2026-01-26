#!/bin/bash

# 인자가 없으면 종료
if [ $# -eq 0 ]; then
    echo "Usage: $0 <branch_name>"
    echo "Example: $0 'new feature 새로운 기능'"
    exit 1
fi

MY_GIT_USER="changgun-lee"

# 브랜치 이름 처리 (공백을 -로 변경, 한글 유지)
RAW_BRANCH_NAME="$@"
BRANCH_NAME="feature/${RAW_BRANCH_NAME// /-}"

echo "Creating and setting up branch: $BRANCH_NAME"
echo "================================================"

# 현재 디렉토리와 하위 디렉토리에서 git 프로젝트 찾기
find . -type d -name ".git" | while read git_dir; do
    # .git 디렉토리의 부모 디렉토리로 이동
    project_dir=$(dirname "$git_dir")
    
    # 절대 경로를 얻어서 project_name 추출
    absolute_path=$(cd "$project_dir" && pwd)
    project_name=$(basename "$absolute_path")
    
    echo ""
    echo "Processing project: $project_name"
    echo "-----------------------------------"

    cd "$project_dir"

    # 0. 현재 작업 중인 내용 stash
    echo "Stashing local changes (if any)..."
    git stash push -u -m "auto-stash before branch setup" >/dev/null 2>&1

    # 1. Remote origin과 upstream 설정
    echo "Setting remotes..."
    git remote set-url origin "https://github.com/${MY_GIT_USER}/${project_name}.git" 2>/dev/null || \
        git remote add origin "https://github.com/${MY_GIT_USER}/${project_name}.git"

    git remote set-url upstream "https://github.com/team-commdev/${project_name}.git" 2>/dev/null || \
        git remote add upstream "https://github.com/team-commdev/${project_name}.git"

    echo "  origin: https://github.com/${MY_GIT_USER}/${project_name}.git"
    echo "  upstream: https://github.com/team-commdev/${project_name}.git"

    # Remote repository 접근 가능 여부 확인
    echo "Verifying remote repositories..."
    
    if ! git ls-remote --exit-code origin >/dev/null 2>&1; then
        echo "ERROR: Cannot access origin repository: https://github.com/changgun-lee/${project_name}.git"
        echo "Please check repository existence and your access permissions."
        exit 1
    fi
    
    if ! git ls-remote --exit-code upstream >/dev/null 2>&1; then
        echo "ERROR: Cannot access upstream repository: https://github.com/team-commdev/${project_name}.git"
        echo "Please check repository existence and your access permissions."
        exit 1
    fi
    
    echo "  Remote repositories verified successfully"

    # Remote 정보 fetch
    echo "Fetching remote branches..."
    git fetch upstream --quiet
    git fetch origin --quiet

    # 2. production 브랜치를 기반으로 새 브랜치 생성 또는 체크아웃
    echo "Setting up branch: $BRANCH_NAME"

    # upstream/production이 존재하는지 확인
    if git show-ref --verify --quiet refs/remotes/upstream/production; then
        # 로컬에 이미 브랜치가 있는지 확인
        if git show-ref --verify --quiet refs/heads/"$BRANCH_NAME"; then
            echo "  Local branch exists, checking out..."
            git checkout "$BRANCH_NAME" --quiet
            echo "  Checked out existing branch: $BRANCH_NAME"
            
            echo "  Note: Branch already exists. If you want to sync with upstream/production,"
            echo "        you may need to merge or rebase manually."
        else
            git checkout -b "$BRANCH_NAME" upstream/production --quiet
            echo "  Branch created from upstream/production"
        fi
        
        # 3. upstream과 origin에 푸시
        echo "Pushing to remotes..."
        git push upstream "$BRANCH_NAME" --quiet
        echo "  Pushed to upstream"
        git push origin "$BRANCH_NAME" --quiet
        echo "  Pushed to origin"
        
        # 4. origin의 브랜치로 트래킹 설정
        git branch --set-upstream-to=origin/"$BRANCH_NAME" "$BRANCH_NAME"
        echo "  Tracking origin/$BRANCH_NAME"
        
    else
        echo "  WARNING: upstream/production branch not found in $project_name"
        echo "  Skipping this project..."
    fi

    # 5. stash 적용 (있을 경우만)
    if git stash list | grep -q "auto-stash before branch setup"; then
        echo "Restoring stashed changes..."
        git stash pop --quiet
    fi
    
    cd - > /dev/null
done

echo ""
echo "================================================"
echo "All projects processed successfully!"
echo "Branch '$BRANCH_NAME' has been created and pushed."