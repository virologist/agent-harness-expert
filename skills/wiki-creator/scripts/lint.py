"""lint.py — 结构体检（别名归一，不再误报；新增多项完整性校验）

用法:
    python lint.py [--root <wiki-root>]

输出 JSON 体检报告，字段：
  page_count / indexed_page_count / topic_count
  orphans               孤立页（零入链）
  dangling_links        悬空链接（**别名归一后**仍指向不存在页）
  nonconforming_links   非法风格链接（大写/中文/下划线/空格/管道显示名）— 已被解析但仍违规
  missing_pages         被 ≥2 个不同页引用的悬空目标（优先补页）
  missing_cross_refs    同主题页未互联（别名感知的启发式）
  duplicate_slugs       跨主题重名 slug（图谱歧义根源）
  entity_type_orphans   frontmatter entity_type 不在 SCHEMA 实体类型清单
  topic_orphans         frontmatter topic 非空但不在 SCHEMA 主题清单
  topic_missing         缺 topic 字段的页（索引会跳过）
  schema_version_drift  页 frontmatter schema_version 与当前 SCHEMA 不一致
  missing_source_section 缺 `## 证据 / 来源` 小节
  unsourced_pages       有 `## 关键论点` 断言但正文零来源锚点（raw/ 或 §）— 覆盖度启发式
  oversized_topics      主题 > 1000 页

注：本脚本只做结构/启发式检查，不做语义判断，也不做检索。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _root import _resolve_root
from _common import (
    MAX_TOPIC_PAGES,
    SOURCE_ANCHOR_RE,
    analyze_page_links,
    build_alias_index,
    load_pages,
    load_schema,
)

# 缺省根延迟到 parse_args 之后探测（理由同 init_wiki.py，避免 import 时崩溃）
DEFAULT_ROOT = None

KEY_POINTS_HEADING = re.compile(r"^##\s*关键论点\s*$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
SOURCE_SECTION_HEADING = re.compile(r"^##\s*(证据\s*/\s*来源|证据|来源)\s*$", re.MULTILINE)


def _section(body: str, heading_re) -> str:
    m = heading_re.search(body)
    return m.group(1) if m else ""


def count_claim_bullets(body: str) -> int:
    """统计 `## 关键论点` 下的 bullet 条数（事实性断言的近似计数）。"""
    sec = _section(body, KEY_POINTS_HEADING)
    if not sec:
        return 0
    n = 0
    for ln in sec.splitlines():
        s = ln.strip()
        if s and s[0] in "-*":
            n += 1
    return n


def has_source_section(body: str) -> bool:
    return bool(SOURCE_SECTION_HEADING.search(body))


def has_source_anchor(body: str) -> bool:
    """正文是否出现任何来源锚点（raw/ 路径 或 §章节 标记）。"""
    return bool(SOURCE_ANCHOR_RE.search(body))


def lint(root: Path) -> dict:
    wiki_dir = root / "wiki"
    pages, decode_errors = load_pages(wiki_dir)  # wiki_dir 不存在时安全返回 ([], [])
    if not wiki_dir.exists():
        return {"error": "wiki/ 不存在", **({"decode_errors": decode_errors} if decode_errors else {})}

    schema = load_schema(wiki_dir)

    # 空目录检查（v1.8.1）：wiki/ 存在但没有页面（schema.json 缺失或无 topics/实体），
    # 说明知识底座只 init 了骨架还没沉淀内容。此时跑全套检查只会产出误导性的
    # 「全 0 结果」——明确报告空态，比静默返回一堆空数组更有诊断价值。
    if not pages:
        return {
            "error": "wiki/ 为空（没有任何页面）",
            "hint": "知识底座尚未沉淀内容：先把阶段产物经 parse_raw.py 入库（见 SKILL.md §4.2 编译流程），再跑 lint。",
            **({"decode_errors": decode_errors} if decode_errors else {}),
        }

    schema_topics = set(schema["topics"].keys())
    entity_types = schema["entity_types"]
    cur_ver = schema["schema_version"]

    page_slugs = {p["slug"] for p in pages}
    alias_index = build_alias_index(pages)

    # 预先解析每页链接（别名归一）；按 path（唯一）缓存，避免重复 slug 键冲突
    analyzed_by_path = {p["path"]: analyze_page_links(p, alias_index, page_slugs) for p in pages}

    # 反链（别名归一后）：target -> set(source slug)
    backlinks = defaultdict(set)
    for p in pages:
        a = analyzed_by_path[p["path"]]
        for key in a["forward"]:
            if key != p["slug"]:
                backlinks[key].add(p["slug"])

    # 1. 孤立页：零入链
    orphans = sorted(p["slug"] for p in pages if not backlinks.get(p["slug"]))

    # 2. 悬空链接（别名归一后仍无对应真实页）
    dangling_inbound = defaultdict(set)   # miss_key -> set(source slug)
    nonconforming = []
    for p in pages:
        a = analyzed_by_path[p["path"]]
        for l in a["links"]:
            if l["is_self"]:
                continue
            if not l["exists"] and not l["resolved_slug"]:
                key = l["miss_key"]
                if key:
                    dangling_inbound[key].add(p["slug"])
            elif not l["exists"] and l["resolved_slug"] and l["resolved_slug"] not in page_slugs:
                dangling_inbound[l["resolved_slug"]].add(p["slug"])
            if not l["conforming"]:
                nonconforming.append({
                    "page": p["slug"],
                    "target": l["target"],
                    "issues": l["issues"],
                    "resolved_to": l["resolved_slug"],
                })
    dangling_links = sorted(dangling_inbound.keys())

    # 3. 缺失页面：被 ≥2 个不同页引用的悬空目标
    missing_pages = sorted(k for k, v in dangling_inbound.items() if len(v) >= 2)

    # 4. 缺失交叉引用：同主题页未互联（别名感知）
    by_topic = defaultdict(list)
    for p in pages:
        if not p["topic_missing"]:
            by_topic[p["topic"]].append(p)
    missing_cross_refs = []
    for topic, group in by_topic.items():
        if len(group) <= 1:
            continue
        for p in group:
            fwd = set(analyzed_by_path[p["path"]]["forward"])
            others = [o["slug"] for o in group if o["slug"] != p["slug"]]
            unlinked = [o for o in others if o not in fwd]
            if len(unlinked) >= 2:
                missing_cross_refs.append(
                    {"page": p["slug"], "topic": topic, "unlinked_same_topic": unlinked[:5]}
                )

    # 5. 重复 slug（图谱歧义）
    by_slug = defaultdict(list)
    for p in pages:
        by_slug[p["slug"]].append(p["path"])
    duplicate_slugs = {s: sorted(ps) for s, ps in by_slug.items() if len(ps) > 1}

    # 6. entity_type 合法性
    entity_type_orphans = []
    for p in pages:
        if entity_types and p["entity_type"] not in entity_types:
            entity_type_orphans.append({"page": p["slug"], "entity_type": p["entity_type"]})

    # 7. topic 孤儿 / 缺 topic
    topic_orphans = [
        {"page": p["slug"], "topic": p["topic"]}
        for p in pages
        if schema_topics and p["topic"] and p["topic"] not in schema_topics
    ]
    topic_missing = sorted(p["path"] for p in pages if p["topic_missing"])

    # 8. schema_version 漂移
    schema_version_drift = [
        {"page": p["slug"], "page_version": p["schema_version"], "current": cur_ver}
        for p in pages
        if cur_ver and p["schema_version"] and p["schema_version"] != cur_ver
    ]

    # 9. 来源：结构性缺失 + 断言覆盖度启发式
    missing_source_section = sorted(
        p["slug"] for p in pages if not has_source_section(p["body"])
    )
    unsourced_pages = []
    for p in pages:
        cb = count_claim_bullets(p["body"])
        if cb > 0 and not has_source_anchor(p["body"]):
            unsourced_pages.append({"page": p["slug"], "claim_bullets": cb})

    # 10. 主题过大
    oversized_topics = [
        {"topic": t, "count": len(g)} for t, g in by_topic.items() if len(g) > MAX_TOPIC_PAGES
    ]

    return {
        "page_count": len(pages),
        "indexed_page_count": sum(1 for p in pages if not p["topic_missing"]),
        "topic_count": len(by_topic),
        "orphans": orphans,
        "dangling_links": dangling_links,
        "nonconforming_links": nonconforming,
        "missing_pages": missing_pages,
        "missing_cross_refs": missing_cross_refs[:20],
        "duplicate_slugs": duplicate_slugs,
        "entity_type_orphans": entity_type_orphans,
        "topic_orphans": topic_orphans,
        "topic_missing": topic_missing,
        "schema_version_drift": schema_version_drift,
        "missing_source_section": missing_source_section,
        "unsourced_pages": unsourced_pages,
        "oversized_topics": oversized_topics,
        **({"decode_errors": decode_errors} if decode_errors else {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="wiki 结构体检")
    parser.add_argument("--root", default=None)
    args = parser.parse_args()
    try:
        root = _resolve_root(args.root)
    except RuntimeError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    result = lint(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    sys.exit(main())
