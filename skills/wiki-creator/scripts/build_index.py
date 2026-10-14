"""build_index.py — 生成 index.md + topics/*.md + 反链 + graph + manifest

用法:
    python build_index.py [--root <wiki-root>]

扫描 wiki/pages/**/*.md，提取 frontmatter，按主题分组、组内按 entity_type 排序，
生成两级索引；解析 [[wikilink]]（**别名归一 + 非法风格识别**）计算反链；
检测重复 slug；递归扫描 raw/（支持子目录）更新 manifest 与 graph。

脚本只做收集、分组、排序、解析、格式化；不做语义创作，不做检索。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _root import detect_wiki_root, normalize_path, safe_mkdir
from _common import (
    ENTITY_ORDER,
    analyze_page_links,
    build_alias_index,
    iter_raw_files,
    load_json,
    load_pages,
    load_schema,
    raw_rel,
    sha256,
)

DEFAULT_ROOT = detect_wiki_root()


def write_index(wiki_dir: Path, pages: list[dict], topics: dict[str, dict]) -> None:
    """生成 wiki/index.md（仅收录有 topic 的页；缺 topic 页不静默丢弃，见 result 报告）。"""
    by_topic = defaultdict(list)
    for p in pages:
        if not p["topic_missing"]:
            by_topic[p["topic"]].append(p)

    lines = [
        "<!-- 本文件由 build_index.py 自动生成，请勿手动编辑 -->",
        "# Wiki 索引",
        "",
        "## 主题",
        "",
    ]
    if not by_topic:
        lines.append("（Wiki 尚未编译，无主题。）")
    else:
        for slug in sorted(by_topic.keys()):
            t = topics.get(slug, {})
            name = t.get("name", slug)
            desc = t.get("desc", "")
            count = len(by_topic[slug])
            desc_str = f"{desc}。" if desc else ""
            lines.append(f"### [[{slug}]] {name}")
            lines.append(f"{desc_str}共 {count} 页。")
            lines.append(f"→ 详见 topics/{slug}.md")
            lines.append("")
    (wiki_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")


def write_topic_indexes(wiki_dir: Path, pages: list[dict], topics: dict[str, dict]) -> None:
    """生成 wiki/topics/<slug>.md（仅收录有 topic 的页）。"""
    topics_dir = wiki_dir / "topics"
    safe_mkdir(topics_dir)

    by_topic = defaultdict(list)
    for p in pages:
        if not p["topic_missing"]:
            by_topic[p["topic"]].append(p)

    # 清理旧索引（仅 *.md），随页面集合刷新
    for old in topics_dir.glob("*.md"):
        old.unlink()

    for slug, group in by_topic.items():
        t = topics.get(slug, {})
        name = t.get("name", slug)
        group.sort(key=lambda p: (ENTITY_ORDER.get(p["entity_type"], 99), p["title"]))

        by_type = defaultdict(list)
        for p in group:
            by_type[p["entity_type"] or "其他"].append(p)

        lines = [
            "<!-- 本文件由 build_index.py 自动生成，请勿手动编辑 -->",
            f"# {name}",
            "",
            f"共 {len(group)} 页。",
            "",
        ]
        for et in sorted(by_type.keys(), key=lambda x: ENTITY_ORDER.get(x, 99)):
            lines.append(f"## {et}")
            for p in by_type[et]:
                summary = p["summary"]
                summary_str = f" — {summary}" if summary else ""
                lines.append(f"- [[{p['slug']}]] {p['title']}{summary_str}")
            lines.append("")
        (topics_dir / f"{slug}.md").write_text("\n".join(lines), encoding="utf-8")


def duplicate_slugs(pages: list[dict]) -> dict[str, list[str]]:
    """检测跨主题重名 slug（同一 stem 出现在多个页）。返回 slug -> [path,...]（仅 >1 的）。"""
    by_slug = defaultdict(list)
    for p in pages:
        by_slug[p["slug"]].append(p["path"])
    return {s: sorted(ps) for s, ps in by_slug.items() if len(ps) > 1}


def build_backlinks(pages: list[dict], alias_index: dict[str, str], page_slugs: set[str]) -> dict:
    """计算反链（**别名归一后**）：target_key -> [source_slug, ...]，自动排除自链接。

    alias/大写等非规范写法会先解析到规范 slug 再入表，避免 'attn' 与 'attention' 碎片化。
    """
    backlinks = defaultdict(list)
    for p in pages:
        a = analyze_page_links(p, alias_index, page_slugs)
        for key in a["forward"]:
            if key == p["slug"]:
                continue
            backlinks[key].append(p["slug"])
    return {k: sorted(set(v)) for k, v in backlinks.items()}


def build_graph(pages: list[dict], alias_index: dict[str, str]) -> dict:
    """构建 graph。

    - entities: slug -> {title,topic,aliases,page}（重复 slug 不覆盖首条，记入 duplicate_slugs）
    - alias_redirects: 归一化别名 -> 规范 slug
    - page_to_sources: **按页面路径**（唯一）而非 slug，避免重名覆盖丢来源
    - source_to_pages: raw 相对路径 -> 页面路径列表
    - duplicate_slugs: slug -> [path,...]
    """
    entities: dict[str, dict] = {}
    page_to_sources: dict[str, list] = {}
    source_to_pages = defaultdict(list)
    dups = duplicate_slugs(pages)
    dup_first: set[str] = set()

    for p in pages:
        slug = p["slug"]
        if slug not in entities:
            entities[slug] = {
                "title": p["title"],
                "topic": p["topic"],
                "aliases": p["aliases"],
                "page": p["path"],
            }
        elif slug in dups:
            dup_first.add(slug)
        page_to_sources[p["path"]] = p["sources"]
        for src in p["sources"]:
            source_to_pages[src].append(p["path"])

    alias_redirects = {k: v for k, v in alias_index.items() if k != v}

    return {
        "entities": entities,
        "alias_redirects": alias_redirects,
        "page_to_sources": page_to_sources,
        "source_to_pages": dict(source_to_pages),
        "duplicate_slugs": dups,
    }


def update_manifest(root: Path, wiki_dir: Path, pages: list[dict]) -> dict:
    """刷新 manifest：递归扫描 raw/ 计算 sha256；标记已被页面引用的文件；记录 schema 版本。"""
    files = {}
    for f in iter_raw_files(root):
        rel = raw_rel(f, root)
        files[rel] = {"sha256": sha256(f), "compiled_at": None}

    page_sources = set()
    for p in pages:
        for s in p["sources"]:
            page_sources.add(s)
    for rel in files:
        if rel in page_sources:
            files[rel]["compiled"] = True

    return {
        "version": 2,
        "schema_version": load_schema(wiki_dir)["schema_version"],
        "files": files,
        "page_count": len(pages),
    }


def build_index(root: Path) -> dict:
    wiki_dir = root / "wiki"
    if not wiki_dir.exists():
        return {"error": "wiki/ 不存在，请先运行 init_wiki.py"}

    pages = load_pages(wiki_dir)
    schema = load_schema(wiki_dir)
    topics = schema["topics"]

    page_slugs = {p["slug"] for p in pages}
    alias_index = build_alias_index(pages)

    write_index(wiki_dir, pages, topics)
    write_topic_indexes(wiki_dir, pages, topics)

    backlinks = build_backlinks(pages, alias_index, page_slugs)
    (wiki_dir / ".backlinks.json").write_text(
        json.dumps(backlinks, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    graph = build_graph(pages, alias_index)
    (wiki_dir / ".graph.json").write_text(
        json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    manifest = update_manifest(root, wiki_dir, pages)
    (wiki_dir / ".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 非法风格链接统计（供报告，不阻断编译）
    nonconforming = 0
    for p in pages:
        a = analyze_page_links(p, alias_index, page_slugs)
        nonconforming += sum(1 for l in a["links"] if not l["conforming"])

    indexed = [p for p in pages if not p["topic_missing"]]
    unindexed = [p["path"] for p in pages if p["topic_missing"]]

    result = {
        "status": "ok",
        "page_count": len(pages),
        "indexed_page_count": len(indexed),
        "unindexed_pages": unindexed,          # 缺 topic 的页（不再静默丢弃）
        "topics": sorted({p["topic"] for p in indexed}),
        "backlinks_count": sum(len(v) for v in backlinks.values()),
        "duplicate_slugs": graph["duplicate_slugs"],
        "nonconforming_links": nonconforming,
        "raw_files": len(manifest["files"]),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 wiki 两级索引 + 元数据")
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    args = parser.parse_args()
    result = build_index(normalize_path(args.root))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
