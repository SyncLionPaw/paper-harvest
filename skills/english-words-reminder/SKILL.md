---
name: english-words-reminder
version: "0.1.0"
description: 帮助用户记录和复习英语单词。当用户说"记住单词 xxx"、"记一下单词 xxx"、"save the word xxx"，或要求"考考我"、"抽查单词"、"复习单词"、"quiz me on my words"时使用。单词保存在 ~/.english-words-reminder/words.txt，每行一个词和它的中文释义、添加日期，末尾数字记录用户没记住的次数。
---

# English Words Reminder

帮用户积累并抽查英语单词。词库文件：`~/.english-words-reminder/words.txt`（目录和文件不存在时由脚本自动创建）。

## 存储格式

每行一个词条，用 Tab 分隔四列：`单词 <Tab> 中文释义 <Tab> 添加日期(YYYY-MM-DD) <Tab> 没记住的次数`。最后一列永远是次数（初始为 0）；释义和日期在添加时一并保存，日期用于按天区分和复习。次数带负号表示该词已被移除（软删除）：词条保留在文件中，但 `list`/`pick`/`count` 都不会再出现。

```
serendipity	意外发现珍奇事物的运气	2026-09-05	2
ephemeral	短暂的；朝生暮死的	2026-09-06	0
in the long run	从长远来看	2026-09-06	-1
```

## 记住单词（触发词："记住单词 xxx"）

1. 先用自己的知识给出该词的中文释义，连同单词一起用脚本添加（已存在则不重复添加；若该词之前被移除过，会自动恢复）：

```bash
"$SKILL_DIR/scripts/words.sh" add serendipity "意外发现珍奇事物的运气"
```

2. 简短回复用户：已记住，并附上释义和一个例句，帮助用户当场记忆。词组/短语作为整体传入，如 `"$SKILL_DIR/scripts/words.sh" add "in the long run" "从长远来看"`。

## 抽查 / 考察用户（触发词："考考我"、"抽查单词"、"复习单词"）

合适的时机：用户明确要求时；或对话开始、用户空闲闲聊时，可以主动提议"要不要抽查几个单词？"（不要每次都问，一天最多主动提议一两次）。

流程：

1. 选出 3–5 个词（没记住次数越多的词越优先被抽中）。输出为 `单词<TAB>释义`，释义用于核对答案，不要提前展示给用户：

```bash
"$SKILL_DIR/scripts/words.sh" pick 3                    # 从全部词中抽
"$SKILL_DIR/scripts/words.sh" pick 3 "$(date +%F)"      # 只抽今天记的词
"$SKILL_DIR/scripts/words.sh" pick 3 2026-09-05         # 只抽某一天记的词
```

用户说"考考我今天/昨天记的词"时，用日期参数限定范围。

2. 把英文单词逐个抛给用户，问中文意思（或反过来给中文问英文，交替进行）。
3. 用户答错或答不上来的词，记录一次"没记住"：

```bash
"$SKILL_DIR/scripts/words.sh" fail ephemeral
```

答对的词不改动。随后把正确答案和例句告诉用户。

## 查看词库

```bash
"$SKILL_DIR/scripts/words.sh" list                  # 按没记住次数降序显示全部
"$SKILL_DIR/scripts/words.sh" list 2026-09-06       # 只看某一天记的词
"$SKILL_DIR/scripts/words.sh" count                 # 总词数
"$SKILL_DIR/scripts/words.sh" count 2026-09-06      # 某一天记了多少个
```

用户问"我记了哪些单词"或"我今天/昨天记了什么"时使用。报告时优先强调没记住次数高的词，建议用户重点复习。

## 删除词条

用户说某个词已经掌握了、不用再提醒时：

```bash
"$SKILL_DIR/scripts/words.sh" remove serendipity
```

这是软删除：次数被加上负号（如 `2` → `-2`），词条仍保留在文件中，但不再出现在 `list`/`pick`/`count` 里。如果之后用户又说"记住单词"同一个词，`add` 会自动去掉负号恢复它（输出 `RESTORED`）。
