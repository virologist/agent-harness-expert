"""init_wiki.py — 创建 wiki/ 骨架 + SCHEMA.md 草稿

用法:
    python init_wiki.py [--root <wiki-root>] [--force] [--reset-schema]

默认 wiki-root 由 _root.detect_wiki_root() 自动探测。

安全语义（重要）：
  - SCHEMA.md 是**用户手写配置**，本脚本**永不覆盖**已存在的 SCHEMA.md。
    即使加 --force，也只重置"可由脚本再生"的派生产物
    （index.md / topics/ / .manifest.json / .graph.json / .backlinks.json），
    绝不动用户 SCHEMA。
  - 仅当显式传入 --reset-schema 时，才会用模板覆盖 SCHEMA.md，
    且覆盖前自动把旧文件备份为 SCHEMA.md.bak，杜绝不可逆丢失。
  - pages/ 下的用户内容任何时候都不会被 init 触碰。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _root import safe_mkdir, _resolve_root


def atomic_write_text(path: Path, text: str) -> None:
    """F-09：唯一 tmp 名 + replace 原子写，避免中断留半截文件。"""
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


# 缺省根延迟到 parse_args 之后探测：模块顶层调 detect_wiki_root() 会在
# team 模式（WORKBUDDY_CONTEXT=team）+ cwd 无项目标记时抛 RuntimeError，
# 导致 `--help` 都无法运行（import 时即崩溃）。
DEFAULT_ROOT = None

SCHEMA_TEMPLATE = """---
schema_version: v1
---

# Wiki 知识库约束配置

> 本文件由 init_wiki.py 生成草稿，由用户编辑确认。LLM 编译前必须先读此文件。
> 详细写法见 references/schema-guide.md。

## 主题边界

覆盖：（待 LLM 通读 raw/ 后归纳，由用户确认）
不覆盖：（待确认）

## 主题清单

> 首次创建时为空，LLM 通读 raw/ 后归纳主题填入，交用户确认。
> 主题永不合并；仅当某主题页面数 > 1000 时由 lint 建议拆分。

| slug | 名称 | 简述 |
|------|------|------|

## 实体类型清单

- 概念
- 方法
- 模型
- 人物
- 机构
- 论文
- 数据集
- 事件

## 成页规则

1. 核心概念、重要方法、知名模型独立成页。
2. 子概念内容不足 200 字时，并入父概念页的子节，不单独建页。
3. 人物仅当在主题内有显著贡献时建页；否则在相关概念页以引用形式出现。
4. 论文仅当本身是里程碑（被反复引用、催生分支）时建页；其余作为来源出现在概念页的 `## 证据 / 来源`。
5. 同一实体有多个名称时，选最通用的作 slug，其余写入 `aliases`，不重复建页。

## 页面模板

见 pages/<topic>/<slug>.md 的统一结构。模板文件：assets/page-template.md。

## 写作风格

- 语言：中文为主，专有名词保留英文原文（如 Transformer、Raft）。
- 语气：客观陈述，不用第一人称，不用营销口吻。
- 引用格式：`## 证据 / 来源` 中每条形如「出自 [[相关概念]]；原文见 raw/<文件名> §<章节>」。
- 长度：单页目标 < 1500 字。
"""

EMPTY_INDEX = (
    "<!-- 本文件由 build_index.py 自动生成，请勿手动编辑 -->\n# Wiki 索引\n\n"
    "（Wiki 尚未编译，无主题。）\n"
)
EMPTY_META = [
    (".manifest.json", {"version": 2, "files": {}, "schema_version": "v1", "page_count": 0}),
    (".graph.json", {"entities": {}, "alias_redirects": {}, "page_to_sources": {},
                     "source_to_pages": {}, "duplicate_slugs": {}}),
    (".backlinks.json", {}),
]


def _write_derived_empty(wiki_dir: Path, force: bool) -> None:
    """重置派生产物（可再生）：index.md 与三个 json。force 时强制重置为初始空值。"""
    index_path = wiki_dir / "index.md"
    if force or not index_path.exists():
        atomic_write_text(index_path, EMPTY_INDEX)
    for name, default in EMPTY_META:
        p = wiki_dir / name
        if force or not p.exists():
            atomic_write_text(p, json.dumps(default, ensure_ascii=False, indent=2))
    # topics/ 目录本身保留；旧索引由 build_index 刷新，init 不清理用户已建页的索引
    safe_mkdir(wiki_dir / "topics")
    safe_mkdir(wiki_dir / "pages")


def init_wiki(root: Path, force: bool = False, reset_schema: bool = False) -> dict:
    """创建 wiki 骨架。返回结构化结果（明确标注 SCHEMA 是否被保护/备份）。"""
    safe_mkdir(root, parents=True)
    safe_mkdir(root / "raw")

    wiki_dir = root / "wiki"
    already = wiki_dir.exists()
    safe_mkdir(wiki_dir)
    safe_mkdir(wiki_dir / "topics")
    safe_mkdir(wiki_dir / "pages")

    schema_path = wiki_dir / "SCHEMA.md"
    schema_action = "created"
    schema_backup = None
    if not schema_path.exists():
        atomic_write_text(schema_path, SCHEMA_TEMPLATE)
        schema_action = "created"
    elif reset_schema:
        backup = wiki_dir / "SCHEMA.md.bak"
        atomic_write_text(backup, schema_path.read_text(encoding="utf-8"))
        schema_backup = str(backup)
        atomic_write_text(schema_path, SCHEMA_TEMPLATE)
        schema_action = "reset-with-backup"
    else:
        schema_action = "preserved"     # 即使 --force 也不覆盖用户 SCHEMA

    if already and not force and not reset_schema:
        _write_derived_empty(wiki_dir, force=False)
        return {
            "status": "exists",
            "root": str(root),
            "wiki_dir": str(wiki_dir),
            "schema": str(schema_path),
            "schema_action": schema_action,
            "message": "wiki/ 已存在，派生产物按需补全；用户 SCHEMA 未改动。如需重置派生产物用 --force，如需重置 SCHEMA（会备份）用 --reset-schema。",
        }

    _write_derived_empty(wiki_dir, force=True)

    return {
        "status": "created" if not already else "forced",
        "root": str(root),
        "wiki_dir": str(wiki_dir),
        "raw_dir": str(root / "raw"),
        "schema": str(schema_path),
        "schema_action": schema_action,
        "schema_backup": schema_backup,
        "message": "wiki 骨架就绪。请上传文件到 raw/，再让 LLM 通读并归纳主题。",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化 wiki 骨架（保护用户 SCHEMA）")
    parser.add_argument("--root", default=None, help="wiki 根目录")
    parser.add_argument("--force", action="store_true",
                        help="重置可再生派生产物（index/topics/json）；不触碰 SCHEMA 与 pages")
    parser.add_argument("--reset-schema", action="store_true",
                        help="用模板覆盖 SCHEMA.md（覆盖前自动备份为 SCHEMA.md.bak）")
    args = parser.parse_args()

    try:
        root = _resolve_root(args.root)
    except RuntimeError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1

    # P2-1：wiki/raw/--root 为普通文件时 safe_mkdir 抛 OSError，
    # 统一输出结构化 JSON 错误（与其它脚本一致），不留裸 traceback。
    try:
        result = init_wiki(root, force=args.force, reset_schema=args.reset_schema)
    except OSError as e:
        print(json.dumps({"status": "error", "error": f"wiki 目录初始化失败（路径为普通文件或不可写）: {e}"},
                         ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in ("created", "exists", "forced") else 1


if __name__ == "__main__":
    sys.exit(main())
