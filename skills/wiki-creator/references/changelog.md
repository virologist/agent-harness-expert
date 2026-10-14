# 变更日志（wiki-creator · 团队特化版）

> 本文件是 wiki-creator 团队特化副本的版本史，从 SKILL.md 移出（给人看，不占智能体常驻加载）。
> 上游为市场技能 wiki-creator；本副本 = 上游快照 + 团队适配层，升级上游时按「diff 上游 + 重放适配层」同步，禁止整体覆盖。

### 1.1.1-wb（团队特化，当前）

- **文档**：原 §10「强约束总览」与 §1「范式红线」90% 重叠，独有 3 条（不走向量、slug 风格统一、schema_version 对齐）已并入 §1，§10 删除——红线只在 §1 定义一次。
- **文档**：变更日志从 SKILL.md 移出至本文件（原 §11，约 2.5KB），SKILL 19.7KB → 约 15KB。
- **补记既有特化（随包构建时引入，此前未记）**：
  - `scripts/_root.py` 新增 `safe_mkdir()`：WorkBuddy 沙箱会拦截 `Path.mkdir(exist_ok=True)` 误抛 PermissionError(EEXIST)，`build_index.py` / `init_wiki.py` 相关调用已改写——上游无此补丁，整体覆盖会重新引入沙箱 bug。
  - 「用户」→「管家节点（用户）」术语映射（对应主理人 MD §四.5）。
  - SKILL.md 新增「运行时脚本路径（必读）」节：独立触发时的脚本绝对路径兜底，团队语境复用主理人下发的 `$WIKI_SCRIPTS`。

---

### 1.1.0（硬化版，上游）

修复评估中发现的图谱完整性问题，全部改动均有 pytest 覆盖（34 用例，位于开发仓库，未随本包分发；包内冒烟验证方式：对任意 `--root` 执行 `lint.py`，确认脚本可运行）：

- **必修**
  - 非法/别名 wikilink 不再静默丢弃：`[[Attention]]`、`[[中文名]]`、`[[slug|显示名]]` 会经**别名归一**解析到目标页（反链不再碎片化），同时由 lint `nonconforming_links` 标记风格问题。
  - slug 全局唯一性检测：`build_index`/`lint` 输出 `duplicate_slugs`；`.graph.json` 的 `page_to_sources` 改为**按页面路径**存储，重名不再互相覆盖丢来源。
  - 别名解析贯穿 backlinks/lint/交叉引用；`.graph.json` 新增 `alias_redirects`。
- **应修**
  - lint 新增 `entity_type_orphans`（实体类型合法性）。
  - 来源校验诚实化：`missing_source_section`（页级结构）+ `unsourced_pages`（有断言但正文零锚点的覆盖度启发式），不再虚标"逐条断言标红"。
  - `init_wiki.py --force` **不再覆盖用户 SCHEMA**，只重置可再生派生产物；新增 `--reset-schema`（覆盖前自动备份 `SCHEMA.md.bak`）。
  - `parse_raw.py`：`.xls` 走 xlrd **真实支持**；旧 `.doc` best-effort（LibreOffice 转 txt，缺则可读文本抢救），任何解析异常都优雅降级并在头部标注"解析质量：降级"，不再只丢一句异常。
- **建议**
  - `raw/` 递归扫描（支持 `raw/子目录/`），diff/manifest/级联受影响页均按相对路径 `raw/sub/a.pdf` 处理。
  - frontmatter 引号感知列表解析（`aliases: ["甲,乙"]` 不再被逗号拆错）；SCHEMA 表格解析排除表头（大小写不敏感）与左对齐分隔行 `|:---|`，垃圾行不作为主题。
  - 无 topic 页在 build/lint **口径统一**（都计入 `page_count`，并列于 `unindexed_pages`/`topic_missing`）；公共逻辑抽取到 `_common.py` 单一真源。
  - `normalize_path` 加平台闸门：仅 `win32` 做 `/c/→C:/` 盘符转换，Linux/macOS 不再误伤 `/c/...` 类路径。
- **可选**
  - `parse_raw.py` docstring 移除不存在的 `--raw-root`；`.json` 加 `## §json` 锚点、无标题纯文本加 `## §raw` 锚点；lint 新增 `schema_version_drift`。

### 1.0.0（初版）

Karpathy 原生 LLM Wiki 范式：零向量、单页为单元、两级索引、前向 wikilink 多跳；创建/更新/查询/体检四工作流。
