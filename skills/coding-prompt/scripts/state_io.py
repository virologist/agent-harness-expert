"""项目级断点状态 I/O（P3-5 落地）。

权威 schema 见 `agents/_state_schema.md`：
- 读写文件：`<project_dir>/.harness-kb/_state.json`
- current_stage 取值：P0 / P1 / P2 / P3 / P4 / complete / aborted
- 必填字段: project / current_stage / completed_stages / last_run_at
            / per_stage_artifacts / open_items
- 选填字段：git_head / retries

提供三个纯 stdlib 函数（任何场景都可调，从不抛隐式异常让上层猜）：

    read_state(project_dir)        -> dict | None
    write_state(project_dir, state) -> None   # 含项目级字段校验
    update_stage(project_dir, stage, artifact_path) -> dict  # 增量更新并落盘

safe_mkdir 与 `wiki-creator/scripts/_root.py::safe_mkdir` 同源：
WorkBuddy 沙箱的 sitecustomize 拦截 Path.mkdir，对已存在目录误抛 EEXIST。
这里统一把「目标已是目录」视为成功，其余错误原样抛出。

本脚本**不**写仓库任何文件、不发起任何子进程、不引入第三方依赖。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 常量与校验
# ---------------------------------------------------------------------------

VALID_STAGES = ("P0", "P1", "P2", "P3", "P4")
TERMINAL_STAGES = ("complete", "aborted")
ALL_STAGES = VALID_STAGES + TERMINAL_STAGES

STATE_FILENAME = "_state.json"
HARNESS_KB_DIRNAME = ".harness-kb"

REQUIRED_KEYS = (
    "project",
    "current_stage",
    "completed_stages",
    "last_run_at",
    "per_stage_artifacts",
    "open_items",
)
OPTIONAL_KEYS = ("git_head", "retries")
ALLOWED_KEYS = REQUIRED_KEYS + OPTIONAL_KEYS

_ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})$")


# ---------------------------------------------------------------------------
# 沙箱安全 mkdir（与 wiki-creator/_root.safe_mkdir 同源）
# ---------------------------------------------------------------------------

def safe_mkdir(path: Path, parents: bool = False) -> None:
    """沙箱安全的 mkdir：已存在目录视为成功，其余错误原样抛出。

    WorkBuddy 沙箱的 sitecustomize 会在 Path.mkdir(exist_ok=True) 对「已存在」
    目录误抛 PermissionError(EEXIST)；同时 Python 3.13+ 在某些边缘情况
    会抛 FileExistsError。这里统一容错。
    """
    try:
        path.mkdir(parents=parents, exist_ok=True)
    except (FileExistsError, PermissionError):
        if path.is_dir():
            return
        raise


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _state_path(project_dir: Path) -> Path:
    """拼出 `<project_dir>/.harness-kb/_state.json`。不触发任何 IO。"""
    return project_dir / HARNESS_KB_DIRNAME / STATE_FILENAME


def _now_iso() -> str:
    """UTC ISO 8601 时间戳（秒精度，Z 后缀）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_state(state: dict[str, Any]) -> None:
    """字段级校验（write_state 用）。失败抛 ValueError，错误信息列出第一个错。"""
    if not isinstance(state, dict):
        raise ValueError(f"state 必须是 dict，实际 {type(state).__name__}")

    missing = [k for k in REQUIRED_KEYS if k not in state]
    if missing:
        raise ValueError(f"state 缺必填字段: {', '.join(missing)}")

    extra = [k for k in state if k not in ALLOWED_KEYS]
    if extra:
        raise ValueError(f"state 含未声明字段: {', '.join(extra)}")

    project = state["project"]
    if not isinstance(project, str) or not project:
        raise ValueError(f"project 必须是非空字符串，实际 {project!r}")

    current_stage = state["current_stage"]
    if current_stage not in ALL_STAGES:
        raise ValueError(
            f"current_stage 必须是 {ALL_STAGES} 之一，实际 {current_stage!r}"
        )

    completed_stages = state["completed_stages"]
    if not isinstance(completed_stages, list) or not all(
        isinstance(s, str) and s in VALID_STAGES for s in completed_stages
    ):
        raise ValueError(
            f"completed_stages 必须是 {list(VALID_STAGES)} 子集的列表，"
            f"实际 {completed_stages!r}"
        )

    last_run_at = state["last_run_at"]
    if not isinstance(last_run_at, str) or not _ISO_UTC_RE.match(last_run_at):
        raise ValueError(
            f"last_run_at 必须是 ISO 8601 UTC 时间戳，实际 {last_run_at!r}"
        )

    per_stage_artifacts = state["per_stage_artifacts"]
    if not isinstance(per_stage_artifacts, dict) or not all(
        isinstance(k, str) and k in VALID_STAGES and isinstance(v, str)
        for k, v in per_stage_artifacts.items()
    ):
        raise ValueError(
            f"per_stage_artifacts 必须是 {{P0..P4: str}} 字典，实际 {per_stage_artifacts!r}"
        )

    open_items = state["open_items"]
    if not isinstance(open_items, list) or not all(
        isinstance(it, str) for it in open_items
    ):
        raise ValueError(f"open_items 必须是 str 列表，实际 {open_items!r}")

    if "retries" in state:
        retries = state["retries"]
        if not isinstance(retries, dict) or not all(
            isinstance(k, str) and k in VALID_STAGES
            and isinstance(v, int) and v >= 0
            for k, v in retries.items()
        ):
            raise ValueError(
                f"retries 必须是 {{P0..P4: 非负整数}} 字典，实际 {retries!r}"
            )


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

def read_state(project_dir: str | Path) -> dict | None:
    """读 `<project_dir>/.harness-kb/_state.json`。

    返回:
        dict — 文件存在且 JSON 合法（不强制字段校验；调用方负责完整 schema）
        None — 文件或目录不存在（全新项目）
    """
    path = _state_path(Path(project_dir))
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} 不是合法 JSON: {e}") from e


def write_state(project_dir: str | Path, state: dict) -> None:
    """写 `<project_dir>/.harness-kb/_state.json`。

    流程:
        1. 校验 state 字段（缺必填字段 → ValueError）
        2. safe_mkdir 创建 `.harness-kb/`（沙箱兼容）
        3. 原子写：先写 `.tmp` 再 rename（保留上次好副本，避免半截 JSON）
        4. 不修改传入的 dict（防御性 copy）
    """
    _validate_state(state)
    target = _state_path(Path(project_dir))
    safe_mkdir(target.parent, parents=True)
    payload = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=False)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(target)


def update_stage(
    project_dir: str | Path,
    stage: str,
    artifact_path: str | Path = "",
) -> dict:
    """增量更新阶段：把 `stage` 标完成 + 推进 current_stage。

    语义:
        - `stage` 必须是 P0/P1/P2/P3/P4 之一
        - 已完成列表追加 stage（去重）
        - per_stage_artifacts[stage] = artifact_path 字符串（空串表示无产出路径）
        - current_stage 推进到 VALID_STAGES 中 stage 的下一个；stage 已是 P4 → 设为 complete
        - last_run_at 用当前 UTC 时间刷新；project 缺失则取 project_dir basename

    写入后返回最终 state（与磁盘一致），便于调用方继续加工。
    """
    if stage not in VALID_STAGES:
        raise ValueError(
            f"stage 必须是 {list(VALID_STAGES)} 之一，实际 {stage!r}"
        )

    project_dir = Path(project_dir)
    state = read_state(project_dir)  # None → 后续初始化
    if state is None:
        # 全新项目：起点统一为 P0；completed 为空，由后续 update_stage 追加
        state = {
            "project": project_dir.resolve().name,
            "current_stage": "P0",
            "completed_stages": [],
            "last_run_at": _now_iso(),
            "per_stage_artifacts": {},
            "open_items": [],
        }

    # 字段补齐（兼容历史无 git_head / retries 的 state.json）
    state.setdefault("project", project_dir.resolve().name)
    state.setdefault("git_head", "")
    state.setdefault("retries", {})

    completed = list(state["completed_stages"])
    if stage not in completed:
        completed.append(stage)
    state["completed_stages"] = completed

    artifacts = dict(state["per_stage_artifacts"])
    if artifact_path:
        # 不 resolve：让调用方掌控绝对/相对形态，避免 symlink/不存在的路径被规范化
        artifacts[stage] = str(artifact_path)
    state["per_stage_artifacts"] = artifacts

    # 推进 current_stage：stage 是 VALID_STAGES 中第 i 个，下一个是 i+1；
    # 越界（stage=P4）→ complete。aborted 不在此推进，留上层显式调用 write_state 写入。
    idx = VALID_STAGES.index(stage)
    if idx + 1 < len(VALID_STAGES):
        state["current_stage"] = VALID_STAGES[idx + 1]
    else:
        state["current_stage"] = "complete"

    state["last_run_at"] = _now_iso()
    write_state(project_dir, state)
    return state


__all__ = [
    "ALL_STAGES",
    "VALID_STAGES",
    "TERMINAL_STAGES",
    "read_state",
    "write_state",
    "update_stage",
    "safe_mkdir",
]
