#!/usr/bin/env python3
"""外部进化库的位置确认、初始化与收录（纯文件变换，不做相关性判断）。

子命令:
    status            报告包内知识库与外部进化库的路径与现状
    init              初始化外部进化库（从包内复制 index.md 作起点，已存在则不动）
    ingest <文件>     把条目文件收录进外部进化库；--row 可同时追加一行到外部 index
    promote <文件>    把外部条目回写进包内（需用户确认后执行，用于发布前合并）

路径规则（与 SKILL.md §0-B 一致）:
    包内（只读）: <SKILL_DIR>/references/knowledge/
    外部（可写）: $WORKBUDDY_CONFIG_DIR/agent-harness-knowledge/  缺省 ~/.workbuddy/agent-harness-knowledge/
"""
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
PKG_KB = SKILL_DIR / "references" / "knowledge"


def ext_dir() -> Path:
    base = os.environ.get("WORKBUDDY_CONFIG_DIR") or (Path.home() / ".workbuddy")
    return Path(base).expanduser() / "agent-harness-knowledge"


def cmd_status(_args) -> int:
    ext = ext_dir()
    print(f"包内知识库（只读）: {PKG_KB}")
    print(f"  存在: {PKG_KB.is_dir()}  条目数: {len(list(PKG_KB.rglob('*.md'))) if PKG_KB.is_dir() else 0}")
    print(f"外部进化库（可写）: {ext}")
    print(f"  存在: {ext.is_dir()}  条目数: {len(list(ext.rglob('*.md'))) if ext.is_dir() else 0}")
    idx = ext / "index.md"
    if not idx.is_file():
        print("  状态: 未初始化（运行 init 创建）")
    else:
        print(f"  状态: 已初始化，索引 {idx}")
    return 0


def cmd_init(_args) -> int:
    ext = ext_dir()
    ext.mkdir(parents=True, exist_ok=True)
    for sub in ("frameworks/core", "models/core", "patterns"):
        (ext / sub).mkdir(parents=True, exist_ok=True)
    idx = ext / "index.md"
    if not idx.is_file():
        src = PKG_KB / "index.md"
        shutil.copyfile(src, idx)
        print(f"已从包内复制索引: {idx}")
    else:
        print(f"索引已存在，未覆盖: {idx}")
    print(f"外部进化库就绪: {ext}")
    return 0


def _dest_for(src: Path, ext: Path) -> Path:
    """按条目 frontmatter 的 type 路由：harness → frameworks/core/，model → models/core/，其余 → patterns/。
    frontmatter 缺失/无 type 时，回退到源路径包含 framework 的旧启发式。"""
    try:
        head = src.read_text(encoding="utf-8")[:600]
        in_fm = False
        for line in head.splitlines():
            s = line.strip()
            if s == "---":
                if in_fm:
                    break
                in_fm = True
                continue
            if in_fm and s.startswith("type:"):
                val = s.split(":", 1)[1].strip().lower()
                if val == "harness":
                    return ext / "frameworks" / "core" / src.name
                if val == "model":
                    return ext / "models" / "core" / src.name
                return ext / "patterns" / src.name
    except OSError:
        pass
    name = src.name
    if "framework" in str(src).replace("\\", "/"):
        return ext / "frameworks" / "core" / name
    return ext / "patterns" / name


def _valid_index_row(row: str) -> bool:
    """索引行最小校验：须是含至少 3 列的 markdown 表格行（防脏行污染索引）。"""
    line = row.strip()
    if not line.startswith("|"):
        return False
    cols = [c for c in line.split("|")[1:-1] if c.strip()]
    return len(cols) >= 3


def cmd_ingest(args) -> int:
    src = Path(args.file).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"文件不存在: {src}")
    ext = ext_dir()
    ext.mkdir(parents=True, exist_ok=True)
    dest = _dest_for(src, ext)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    print(f"已收录: {dest}")
    if args.row:
        if not _valid_index_row(args.row):
            raise SystemExit("索引行不合格：须是以 | 开头、含至少 3 列的 markdown 表格行（防脏行污染索引）")
        idx = ext / "index.md"
        if not idx.is_file():
            cmd_init(args)
        with idx.open("a", encoding="utf-8") as fh:
            fh.write(args.row.rstrip("\n") + "\n")
        print(f"已追加索引行: {idx}")
    return 0


def cmd_promote(args) -> int:
    """把外部条目回写进包内（发布前合并用）。默认只打印将要写入的目标，需 --apply 才落盘。"""
    src = Path(args.file).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"文件不存在: {src}")
    dest = _dest_for(src, PKG_KB)
    if not args.apply:
        print(f"[dry-run] 将写入: {dest}（追加 --apply 执行）")
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    print(f"已回写包内: {dest}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="外部进化库管理工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="报告两套知识库路径与现状").set_defaults(func=cmd_status)
    sub.add_parser("init", help="初始化外部进化库").set_defaults(func=cmd_init)

    p_ing = sub.add_parser("ingest", help="收录条目到外部进化库")
    p_ing.add_argument("file")
    p_ing.add_argument("--row", help="同时追加到外部 index.md 的表格行")
    p_ing.set_defaults(func=cmd_ingest)

    p_pro = sub.add_parser("promote", help="把外部条目回写进包内（发布前合并）")
    p_pro.add_argument("file")
    p_pro.add_argument("--apply", action="store_true")
    p_pro.set_defaults(func=cmd_promote)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
