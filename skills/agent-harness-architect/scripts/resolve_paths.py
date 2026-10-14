#!/usr/bin/env python3
"""定位 agent-harness-architect 的 SKILL_DIR 与 EXT_DIR（纯标准库，零依赖）。

解析顺序（SKILL.md §0-A 唯一实现处）：
  1. 环境注入值（宿主注入的 skill 目录）
  2. 自身 __file__ 反推（本脚本位于 <SKILL_DIR>/scripts/ 下）
  3. 文件搜索兜底（**/skills/agent-harness-architect/SKILL.md）
     —— 多命中：列出全部候选并 exit 2，禁止静默取第一条

输出（stdout，两行）：
  SKILL_DIR=<绝对路径>
  EXT_DIR=<绝对路径>

退出码：0 成功；2 搜索多命中（候选列在 stderr，需用户裁决）；1 未能定位。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

SKILL_NAME = "agent-harness-architect"
KNOWLEDGE_DIRNAME = "agent-harness-knowledge"
# 宿主可能注入的环境变量名，按序尝试
ENV_CANDIDATES = ("SKILL_DIR", "SKILL_BASE_DIR", "WORKBUDDY_SKILL_DIR")
# 搜索时剪枝的目录名（避免扫 node_modules / 缓存）
PRUNE_DIRS = {
    "__pycache__", ".git", "node_modules", ".venv", "venv",
    "Library", "Application Support", "Caches",
}
# 单根最多扫描的条目数（防超大数据目录拖死）
MAX_SCAN = 20000


def _env_skill_dir() -> Path | None:
    for name in ENV_CANDIDATES:
        raw = os.environ.get(name)
        if not raw:
            continue
        p = Path(raw).expanduser()
        if (p / "SKILL.md").is_file():
            return p.resolve()
    return None


def _self_skill_dir() -> Path:
    # resolve_paths.py 位于 <SKILL_DIR>/scripts/ 下
    return Path(__file__).resolve().parent.parent


def _ext_dir() -> Path:
    base = os.environ.get("WORKBUDDY_CONFIG_DIR")
    root = Path(base).expanduser() if base else Path.home() / ".workbuddy"
    return (root / KNOWLEDGE_DIRNAME).resolve()


def _iter_dirs(root: Path):
    """受控遍历：剪枝 + 计数封顶。"""
    count = 0
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
        yield Path(dirpath)
        count += 1
        if count >= MAX_SCAN:
            return


def _search_skill_dirs() -> list:
    """在合理根目录中搜索 skills/<SKILL_NAME>/ 目录。"""
    roots = [Path.cwd().resolve(), Path.home() / ".workbuddy"]
    hits = []
    for root in roots:
        if not root.is_dir():
            continue
        for d in _iter_dirs(root):
            if d.name == SKILL_NAME and d.parent.name == "skills":
                if (d / "SKILL.md").is_file() and d.resolve() not in hits:
                    hits.append(d.resolve())
    return hits


def main() -> int:
    skill_dir = _env_skill_dir() or _self_skill_dir()
    if not (skill_dir / "SKILL.md").is_file():
        # 注入值/自身反推都失败 → 文件搜索兜底
        hits = _search_skill_dirs()
        if len(hits) > 1:
            sys.stderr.write("SKILL_DIR 多命中（本机存在多份副本），请用户选择：\n")
            for h in hits:
                sys.stderr.write(f"  - {h}\n")
            return 2
        if len(hits) == 1:
            skill_dir = hits[0]
        else:
            sys.stderr.write("未能定位 SKILL_DIR（无注入值、脚本不在包内、搜索无命中）\n")
            return 1
    sys.stdout.write(f"SKILL_DIR={skill_dir}\n")
    sys.stdout.write(f"EXT_DIR={_ext_dir()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
