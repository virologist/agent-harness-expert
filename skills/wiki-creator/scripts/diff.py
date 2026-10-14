"""diff.py — 哈希比对 → new/changed + 受影响已有页清单（raw/ 递归）

用法:
    python diff.py [--root <wiki-root>]

输出 JSON：
{
  "schema_version_changed": bool,
  "new_schema_version": str,
  "new":      [raw_rel, ...],      # manifest 无记录
  "changed":  [raw_rel, ...],      # hash 变化 → 触发级联
  "unchanged":[raw_rel, ...],
  "affected_pages": [page_path, ...]   # 仅 changed 文件经 source_to_pages 反查到的页
}

raw_rel 形如 "raw/a.pdf" 或 "raw/sub/b.docx"（支持子目录）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _root import detect_wiki_root, normalize_path
from _common import iter_raw_files, load_json, load_schema, raw_rel, sha256

DEFAULT_ROOT = detect_wiki_root()


def diff(root: Path) -> dict:
    wiki_dir = root / "wiki"
    manifest = load_json(wiki_dir / ".manifest.json", {"files": {}, "schema_version": "v1"})
    graph = load_json(
        wiki_dir / ".graph.json",
        {"entities": {}, "page_to_sources": {}, "source_to_pages": {}},
    )

    files_state = manifest.get("files", {})
    new_files, changed_files, unchanged_files = [], [], []

    raw_files = iter_raw_files(root)          # 递归
    for f in raw_files:
        rel = raw_rel(f, root)
        h = sha256(f)
        prev = files_state.get(rel)
        if prev is None:
            new_files.append(rel)
        elif prev.get("sha256") != h:
            changed_files.append(rel)
        else:
            unchanged_files.append(rel)

    # 受影响已有页：仅 changed 文件经 source_to_pages 反查（page_to_sources 已按路径存储，避免重名丢来源）
    source_to_pages = graph.get("source_to_pages", {})
    affected = set()
    for src in changed_files:
        for page in source_to_pages.get(src, []):
            affected.add(page)

    # schema 版本
    schema_version = load_schema(wiki_dir)["schema_version"]
    schema_changed = manifest.get("schema_version", "v1") != schema_version
    if schema_changed:
        # schema 变更视为全量 new（全量重编译）
        new_files = [raw_rel(f, root) for f in raw_files]
        changed_files = []
        affected = set()

    return {
        "schema_version_changed": schema_changed,
        "new_schema_version": schema_version,
        "new": new_files,
        "changed": changed_files,
        "unchanged": unchanged_files,
        "affected_pages": sorted(affected),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="raw 文件哈希比对（递归）")
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    args = parser.parse_args()
    result = diff(normalize_path(args.root))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
