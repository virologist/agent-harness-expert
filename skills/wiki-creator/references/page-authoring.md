# 单页写作规范

> 本文档在 LLM 创建 / 修改任何 `pages/<topic>/<slug>.md` 前必读。模板见 `assets/page-template.md`。

## 1. 文件路径与命名

- 路径：`wiki/pages/<topic>/<slug>.md`，其中 `<topic>` 必须命中 SCHEMA.md 主题清单中的 slug。
- `<slug>` 一律 **kebab-case 英文**，如 `transformer`、`large-language-model`、`raft-consensus`。
- 文件名 = slug + `.md`。
- 中文实体走 `aliases` 字段，不直接做 slug。

## 2. Frontmatter（必填）

```yaml
---
title: Transformer              # 实体的显示名，可中可英
topic: deep-learning            # 必须命中 SCHEMA 主题清单
entity_type: 概念               # 必须命中 SCHEMA 实体类型清单
aliases: [Transformer 架构]      # 同实体别名，可空 []
sources: [raw/paper-a.pdf]      # 来源文件列表，路径相对 wiki 根
schema_version: v3              # 当前 SCHEMA 的版本号
---
```

强约束：
- `topic` 必须在 SCHEMA 主题清单中，否则 lint 报 `topic_orphans`。
- `entity_type` 必须在 SCHEMA 实体类型清单中。
- `sources` 必须列出所有引用的 raw 文件。
- `schema_version` 与当前 SCHEMA.md 的 `schema_version` 一致。

## 3. 正文章节（统一结构）

```markdown
# <Title>

## 摘要
（1-2 句话，供主题索引抓取。最多 2 句，保证索引紧凑。）

## 定义
（核心定义 / 概念边界 / 与近义实体的区分。）

## 关键论点
- 论点 1
- 论点 2
- ...

## 证据 / 来源
- 出自 [[相关概念]] 机制；原文见 raw/paper-a.pdf §3
- 出自 [[某方法]]；原文见 raw/notes.md §heading-2

## 关联
- 基础：[[attention]], [[positional-encoding]]
- 对比：[[rnn]], [[cnn-nlp]]
- 应用：[[bert]], [[gpt]]
```

### 3.1 章节约束

- `## 摘要` **最多 2 句**，build_index.py 抓取它作为主题索引条目的描述。
- `## 定义` 写核心定义，不写应用细节。
- `## 关键论点` 用 bullet list，每条 ≤ 60 字。
- `## 证据 / 来源` 每条事实应带来源锚点（`raw/<文件> §<章节>`）；缺此小节 → lint `missing_source_section`，有 `## 关键论点` 却零锚点 → lint `unsourced_pages`（覆盖度启发式）。
- `## 关联` 用三类分组：基础 / 对比 / 应用，每项是 `[[slug]]`。

### 3.2 长度

单页目标 **< 1500 字**（含 frontmatter）。超出则考虑拆分实体。

## 4. Wikilink 约定

- 一律 `[[kebab-case-english-slug]]`，如 `[[large-language-model]]`。
- 应写成小写规范 slug，不要用 `[[中文]]`、`[[Title Case]]`、`[[snake_case]]`、`[[slug|显示名]]`。
- wikilink **可跨主题**——`pages/deep-learning/transformer.md` 可以链接 `[[distributed-systems/parameter-server]]`。
- **别名归一（1.1.0）**：命中 `aliases`/`title`/大小写变体的链接会被解析重定向到主 slug，反链不再碎片化；`.graph.json` 的 `alias_redirects` 记录映射。
- **非规范写法不再静默丢弃（1.1.0）**：`[[Attention]]`、`[[中文名]]`、`[[slug|显示名]]` 仍会被解析到目标页，但 lint 会列入 `nonconforming_links`（带 `uppercase`/`non-ascii`/`space-or-underscore`/`pipe-display`/`malformed-slug` 原因）要求改正。
- wikilink **别名归一后仍**指向不存在的页 → lint 报 `dangling_links`；被 ≥2 页引用的悬空目标另列 `missing_pages`（优先补页）。
- 同一 slug 不得跨主题重名，否则 `duplicate_slugs`（图谱歧义）。

## 5. 防幻觉规则

1. **每条事实应标注来源**：文件名 + §章节。lint 做**页级覆盖度启发式**：缺 `## 证据 / 来源` 小节 → `missing_source_section`；有 `## 关键论点` 断言但正文零来源锚点（`raw/…` 或 `§…`）→ `unsourced_pages`。**这是提示而非逐句强制归因**——是否逐条给来源仍靠作者自觉。
2. **不脑补**：raw 文件没写的不要写。如需补充，标 `（待补全）` 并在 lint 报告提示。
3. **矛盾不覆盖**：发现与已有页冲突时，写 `wiki/.conflicts.md` 等用户裁决，绝不静默覆盖。
4. **不在正文写反链**：反链由脚本维护，注入到 `.backlinks.json`，LLM 不写回正文。
5. **不写营销口吻**：客观陈述，不用"革命性"、"颠覆性"等词。

## 6. 来源标注格式

每条来源行：

```
- 出自 [[相关实体]]；原文见 raw/<文件名> §<章节>
```

章节标记由 `parse_raw.py` 自动生成（1.1.0 与实现对齐）：
- PDF：`§page-N`
- XLSX / XLS：`§sheet-<sheet-name>`
- CSV：`§table`
- DOCX：`§heading-N`（段落标题）+ `§table-N`（表格）
- 旧 DOC：`§doc-converted`（经 LibreOffice）或 `§raw`（可读文本抢救）；头部标"解析质量：降级"
- PPTX：`§slide-N`（+ 幻灯片内表格）
- HTML：`§html-body`
- Markdown：`§heading-N`；无标题的纯文本 → `§raw`
- JSON：`§json`

示例：
```
- 出自 [[attention]] 机制；原文见 raw/paper-a.pdf §page-3
- 出自 [[bert]] 模型；原文见 raw/notes.md §heading-2
```

## 7. 实体粒度判定

参考 SCHEMA.md 的成页规则。判定流程：

1. raw 中出现的实体是否在主题边界内？否 → 不建页。
2. 是否是核心概念 / 重要方法 / 知名模型？是 → 独立成页。
3. 内容是否 < 200 字？是 → 并入父概念页子节，不单独建页。
4. 是否是人物 / 论文？满足"显著贡献 / 里程碑"才建页，否则作引用。
5. 是否同实体多名？选最通用名做 slug，其余入 `aliases`，不重复建页。

## 8. 常见错误

| 错误 | 检测（lint 字段，1.1.0 实测） | 修正 |
|---|---|---|
| frontmatter 缺 topic | `topic_missing`（不入索引） | 补 `topic` |
| topic 不在 SCHEMA | `topic_orphans` | 改 topic 或经确认加 SCHEMA 主题 |
| entity_type 非法 | `entity_type_orphans` | 用 SCHEMA 实体类型清单内的值 |
| schema_version 与 SCHEMA 不一致 | `schema_version_drift` | 对齐当前 SCHEMA 版本 |
| 摘要 > 2 句 | 人工审查 / 索引膨胀 | 精简到 2 句 |
| wikilink 用中文/大写/管道 | `nonconforming_links`（已解析但风格违规） | 改 kebab-case 英文 slug |
| wikilink 指向不存在页 | `dangling_links` / `missing_pages`（≥2 引用） | 建页或改链接 |
| slug 跨主题重名 | `duplicate_slugs` | 用 `[[topic/slug]]` 消歧或改名 |
| 无来源 | `missing_source_section` / `unsourced_pages`（覆盖度启发式） | 补 `## 证据 / 来源` + §锚点 |
| 正文写反链 | 与脚本互相覆盖 | 删除，反链只在 `.backlinks.json` |
| 单页 > 1500 字 | 人工审查 | 拆分实体 |
