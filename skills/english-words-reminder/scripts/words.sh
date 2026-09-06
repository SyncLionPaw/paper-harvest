#!/bin/bash
# english-words-reminder 词库管理脚本
# 词库: ~/.english-words-reminder/words.txt
# 格式: 单词<TAB>中文释义<TAB>没记住次数（释义可为空；次数永远在最后一列）
# 次数带负号表示该词已移除（软删除）：保留在文件中，但 list/pick/count 不再出现

set -euo pipefail

DIR="$HOME/.english-words-reminder"
FILE="$DIR/words.txt"

mkdir -p "$DIR"
touch "$FILE"

find_line() {
    # 精确匹配第一列，输出行号；不存在返回非零
    awk -F '\t' -v w="$1" '$1 == w { print NR; found=1; exit } END { if (!found) exit 1 }' "$FILE"
}

cmd="${1:-}"
shift || true

case "$cmd" in
    add)
        word="${1:-}"
        meaning="${2:-}"
        [ -n "$word" ] || { echo "usage: words.sh add <word> [meaning]"; exit 1; }
        if find_line "$word" >/dev/null; then
            line="$(find_line "$word")"
            if awk -F '\t' -v n="$line" 'NR==n{ exit ($NF ~ /^-/ ? 0 : 1) }' "$FILE"; then
                # 已移除的词：去掉负号恢复
                awk -F '\t' -v n="$line" 'BEGIN{OFS="\t"} NR==n{ sub(/^-/, "", $NF) } { print }' "$FILE" > "$FILE.tmp"
                mv "$FILE.tmp" "$FILE"
                echo "RESTORED: $word"
            else
                echo "EXISTS: $word"
            fi
        else
            printf '%s\t%s\t0\n' "$word" "$meaning" >> "$FILE"
            echo "ADDED: $word"
        fi
        ;;
    fail)
        word="$*"
        [ -n "$word" ] || { echo "usage: words.sh fail <word>"; exit 1; }
        line="$(find_line "$word" || true)"
        if [ -z "$line" ]; then
            echo "NOT_FOUND: $word"
            exit 1
        fi
        awk -F '\t' -v n="$line" 'BEGIN{OFS="\t"} NR==n{ if ($NF ~ /^-/) { exit 2 } $NF = $NF + 1 } { print }' "$FILE" > "$FILE.tmp" || {
            rc=$?
            rm -f "$FILE.tmp"
            if [ "$rc" -eq 2 ]; then echo "REMOVED_WORD: $word (已移除，可用 add 恢复)"; fi
            exit 1
        }
        mv "$FILE.tmp" "$FILE"
        new_count="$(awk -F '\t' -v n="$line" 'NR==n{ print $NF }' "$FILE")"
        echo "FAILED: $word (count=$new_count)"
        ;;
    remove)
        word="$*"
        [ -n "$word" ] || { echo "usage: words.sh remove <word>"; exit 1; }
        line="$(find_line "$word" || true)"
        if [ -z "$line" ]; then
            echo "NOT_FOUND: $word"
            exit 1
        fi
        # 软删除：次数加负号标记为已移除，词条保留在文件中，list/pick 不再出现
        awk -F '\t' -v n="$line" 'BEGIN{OFS="\t"} NR==n && $NF !~ /^-/ { $NF = "-" $NF } { print }' "$FILE" > "$FILE.tmp"
        mv "$FILE.tmp" "$FILE"
        new_count="$(awk -F '\t' -v n="$line" 'NR==n{ print $NF }' "$FILE")"
        echo "REMOVED: $word (count=$new_count)"
        ;;
    list)
        if [ ! -s "$FILE" ]; then
            echo "词库为空"
            exit 0
        fi
        # 跳过已移除（次数为负）的词，按没记住次数降序
        awk -F '\t' 'BEGIN{OFS="\t"} $NF !~ /^-/ { print $NF, $0 }' "$FILE" | sort -rn | cut -f2-
        ;;
    count)
        awk -F '\t' '$NF !~ /^-/{ c++ } END{ print c+0 }' "$FILE"
        ;;
    pick)
        n="${1:-3}"
        if [ ! -s "$FILE" ]; then
            echo "词库为空"
            exit 0
        fi
        # 按 没记住次数+1 加权随机抽取，答错多的词更容易被抽中
        # 已移除（次数为负）的词权重为 0，不会被抽中
        # 输出: 单词<TAB>中文释义（释义供出题者核对答案，不要直接展示给用户）
        awk -F '\t' -v n="$n" 'BEGIN{OFS="\t"}
        {
            words[NR] = $1
            meanings[NR] = (NF >= 3 ? $2 : "")
            w[NR] = ($NF ~ /^-/) ? 0 : $NF + 1
            total += w[NR]
            count = NR
        }
        END {
            srand()
            picked = 0
            while (picked < n && picked < count && total > 0) {
                r = rand() * total
                acc = 0
                for (i = 1; i <= count; i++) {
                    acc += w[i]
                    if (r <= acc) {
                        print words[i], meanings[i]
                        total -= w[i]
                        w[i] = 0
                        picked++
                        break
                    }
                }
            }
        }' "$FILE"
        ;;
    *)
        echo "usage: words.sh {add|fail|remove|list|count|pick} [args]"
        exit 1
        ;;
esac
