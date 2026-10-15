#!/usr/bin/env python3
"""_harness_kb_init.py — 项目级 `<项目>/.harness-kb/` 目录初始化（P3-7）

WHY: 团队语境下多个产物路径都假设 `<项目>/.harness-kb/` 已存在——
  - learnings.md（P1-4 闭环，编码/测试工程师写入）
  - mode2-log.md（P3-4 协议，Mode 2 告警落盘）
  - _state.json（P3-5 占位，断点状态机）
  - inbox/（待处理 raw 资料）
首次跑流程时主理人需手工建 `.harness-kb/`，是已知失败源之一
（v1.2 报告 N2 亲验）。本脚本统一初始化骨架，幂等可重跑。

WHAT: 在项目根执行时自动创建：
  .harness-kb/
  ├── learnings.md        # 编码经验层（P1-4 闭环）
  ├── mode2-log.md        # Mode 2 告警落盘（P3-4 协议）
  ├── _state.json         # 断点状态机占位（P3-5 接管）
  └── inbox/              # 收件箱（待处理 raw 资料）

与 wiki-creator 的 `scripts/init_wiki.py` 对齐：
  - safe_mkdir 兼容 WorkBuddy 沙箱 EEXIST 误报（标准库 mkdir(exist_ok=True)
    被 sitecustomize 拦截为 PermissionError 的场景）
  - 默认幂等：目录已存在时不覆盖任何文件；--force 重建 4 个产物（inbox/ 不清空）

用法:
    python3 agents/_harness_kb_init.py <project_root> [--force]

退出码: 0 成功；1 参数错误。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def safe_mkdir(path: Path, parents: bool = False) -> None:
    """沙箱安全的 mkdir（WorkBuddy 运行时补丁）。

    WorkBuddy 沙箱的 sitecustomize 拦截了 Path.mkdir，对「目录已存在」的
    mkdir(exist_ok=True) 会误抛 PermissionError(EEXIST)（标准库本应静默成功）。
    这里统一把「目标已是目录」视为成功，其余错误原样抛出。
    与 `wiki-creator/scripts/_root.py:safe_mkdir` 保持同一实现（双副本各有
    自包含 init 工具，便于不依赖 sys.path 跨目录调用）。
    """
    try:
        path.mkdir(parents=parents, exist_ok=True)
    except (FileExistsError, PermissionError):
        if path.is_dir():
            return
        raise


# learnings.md 样板 — 与 coding-prompt/references/learnings.md 对齐
LEARNINGS_TEMPLATE = """# 项目内经验沉淀（learnings）

> 团队语境（agent-harness-expert）下编码/测试工程师经验层唯一可写位置。
> 写入协议与晋升路径见 `coding-prompt/references/evolution.md`「写入位置」与
> `coding-prompt/references/learnings.md`「Pattern-Key 跟踪表」。
> 本目录由 `agents/_harness_kb_init.py` 初始化；首次跑流程时由主理人执行一次。
>
> 表头与分节沿用 `coding-prompt/references/learnings.md` 基线格式，便于两边对齐。

## 状态

当前无历史沉淀（首次采集见 `coding-prompt/references/learnings.md` §第 1 步）。

## Pattern-Key 跟踪表

| Pattern-Key | 首次见 | 复现数 | 状态 | 来源 | 简述 |
|---|---|---|---|---|---|
| _（待首批采集）_ | | | | | |

## 被验证有效的模式

<!-- 条目格式：2-4 行。规则一句话 + 触发场景。不要冗长叙述。 -->

## 反模式（踩过的坑）

<!-- 读此分节纳入 Mode 2 主动监控范围（coding-prompt SKILL.md Mode 2）。 -->

## 个人偏好

<!-- 管家节点明确表达过的偏好。 -->
"""

# mode2-log.md 样板 — 与 coding-prompt/SKILL.md「P3-4 跨 P 状态承继」表格对齐
MODE2_LOG_TEMPLATE = """# Mode 2 告警日志（P3-4 跨 P 状态承继）

> 由编码工程师（agent-harness-coder）在 Mode 2 触发 D11-D16 时追加；测试工程师
> P3 开工先读，纳入「编码期发现」节；主理人阶段收尾通读评估告警模式。
> 触发条件与列含义见 `coding-prompt/SKILL.md`「P3-4 跨 P 状态承继」段。
>
> 本目录由 `agents/_harness_kb_init.py` 初始化。

| ts | signal | detail |
|----|--------|--------|
| _（待首批告警）_ | | |
"""

# _state.json 最小占位 — schema 由 P3-5 协议（agents/_state_schema.md）接管升级
# 字段含义：
#   stage: 当前阶段（None 表示未启动；P3-5 接管后填 P0/P1/P2/P3/P4 等）
#   last_updated: 最近一次状态写入时间（UTC ISO 8601）；首次 init 填初始化时间
STATE_PLACEHOLDER = {"stage": None, "last_updated": None}


def init(project_root: Path, force: bool = False) -> dict:
    """初始化 `<project_root>/.harness-kb/` 骨架。

    创建 4 个产物（默认幂等；--force 重建 3 个文件，inbox/ 不清空）：
      - learnings.md
      - mode2-log.md
      - _state.json
      - inbox/  （空目录）

    Returns:
        dict with keys: status, kb_dir, created, preserved, force, message
    """
    if not project_root.exists() or not project_root.is_dir():
        raise FileNotFoundError(f"项目根不存在或不是目录: {project_root}")

    kb = project_root / ".harness-kb"
    kb_was_new = not kb.exists()
    safe_mkdir(kb, parents=True)
    safe_mkdir(kb / "inbox")

    # _state.json 初始化时写入当前 ISO 时间戳，便于「至少被 touched 过」自检
    state_payload = {
        "stage": None,
        "last_updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    artifacts: dict[str, str] = {
        "learnings.md": LEARNINGS_TEMPLATE,
        "mode2-log.md": MODE2_LOG_TEMPLATE,
        "_state.json": json.dumps(state_payload, ensure_ascii=False, indent=2),
    }

    created: list[str] = []
    preserved: list[str] = []
    for name, content in artifacts.items():
        p = kb / name
        if p.exists() and not force:
            preserved.append(name)
            continue
        p.write_text(content, encoding="utf-8")
        created.append(name)

    return {
        "status": "ok",
        "kb_dir": str(kb),
        "kb_was_new": kb_was_new,
        "created": created,
        "preserved": preserved,
        "force": force,
        "message": (
            "首次跑流程前由主理人执行一次即可；后续 P1-4/P3-4 由对应成员写入对应文件。"
            if kb_was_new
            else ".harness-kb/ 已存在；默认幂等（未覆盖已有文件）。--force 重建 3 个文件骨架。"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="初始化 <项目>/.harness-kb/ 骨架（团队语境的编码/告警/状态沉淀处）"
    )
    parser.add_argument(
        "project_root",
        help="项目根路径（将创建其下的 .harness-kb/）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="重建 3 个文件骨架（learnings/mode2-log/_state），inbox/ 不清空",
    )
    args = parser.parse_args()

    try:
        result = init(Path(args.project_root).resolve(), force=args.force)
    except FileNotFoundError as e:
        print(json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
