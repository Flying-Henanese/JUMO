#!/bin/bash

# 统计src目录下所有.py文件的有效代码行数（排除注释）
total_lines=0

echo "正在统计有效代码行数（排除注释）..."

# 遍历src目录及其子目录中的.py文件
while IFS= read -r file; do
    # 使用grep排除空行和注释行
    lines=$(grep -v "^\s*#" "$file" | grep -v "^\s*$" | wc -l)
    total_lines=$((total_lines + lines))
    
    # 输出单个文件统计
    echo "$file: $lines 行"
done < <(find src -type f -name "*.py")

# 输出总行数
echo "总有效代码行数: $total_lines 行"