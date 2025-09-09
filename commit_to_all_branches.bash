# 7ee103ec2c89f56354fab6dbb650d559782d3ce7

#!/bin/bash

# 检查是否提供了 commit ID 参数
if [ -z "$1" ]; then
  echo "❌ 请提供 commit ID 作为参数。"
  echo "用法: $0 <commit_id>"
  exit 1
fi

COMMIT_ID="$1"
CURRENT_BRANCH=$(git branch --show-current)
BRANCHES=$(git for-each-ref --format='%(refname:short)' refs/heads/)

echo "🔍 开始将提交 $COMMIT_ID cherry-pick 到所有本地分支..."
echo

for BRANCH in $BRANCHES; do
  echo "➡️  切换到分支: $BRANCH"
  git checkout "$BRANCH"

  if git cherry-pick "$COMMIT_ID"; then
    echo "✅ 成功应用到 $BRANCH"
  else
    echo "❌ cherry-pick 到 $BRANCH 失败，正在中止并还原"
    git cherry-pick --abort
  fi

  echo
done

git checkout "$CURRENT_BRANCH"
echo "🔙 已切回原始分支: $CURRENT_BRANCH"
