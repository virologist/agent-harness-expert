# 项目状态机 schema（v1）

每个项目根的 `.harness-kb/_state.json` 必须按下表结构记录当前断点状态，
供主理人开工前/阶段收尾时读写，避免「轮次耗尽，产出不完整」靠自然语言标注带来的歧义。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| project | str | 是 | 项目标识（路径 basename） |
| current_stage | enum | 是 | P0 / P1 / P2 / P3 / P4 / complete / aborted |
| completed_stages | list | 是 | 已完成阶段（按顺序），元素取 P0/P1/P2/P3/P4 |
| last_run_at | str | 是 | ISO 8601 UTC 时间戳（最近一次写入时间） |
| per_stage_artifacts | dict | 是 | 阶段 → 产出路径映射（key=P0..P4, value=绝对路径字符串） |
| open_items | list | 是 | 当前 open items（来自 `_handoff_schema.md` 的 `open_items` 字段） |
| git_head | str | 否 | 最近 commit SHA（短 7 位即可，方便跨设备对账） |
| retries | dict | 否 | 阶段 → 返工轮次映射（key=P0..P4, value=非负整数） |

## 写入位置与时点

- **路径**：`<项目根>/.harness-kb/_state.json`（项目级，不放专家包内）
- **开工前**：主理人先 `read_state(project_dir)` 确认断点；若 `_state.json` 不存在，
  视为全新项目，从 `current_stage=P0` 起阶段，`completed_stages=[]`
- **阶段收尾时**：主理人写入 `{last_run_at, current_stage, completed_stages, per_stage_artifacts, open_items, git_head, retries}`
- **轮次耗尽 / aborted**：撞限后必须立刻更新 `current_stage=aborted`（或回退到出问题的阶段），
  `open_items` 追加 `turns_exhausted:<stage>` 一条，等候管家节点裁决续跑/重做

## 读写工具

主理人与成员通过 `skills/coding-prompt/scripts/state_io.py` 三个纯 stdlib 函数读写：

- `read_state(project_dir)` → `dict | None`
- `write_state(project_dir, state)` → 落盘 `<项目>/.harness-kb/_state.json`
- `update_stage(project_dir, stage, artifact_path)` → 增量更新 `current_stage` / `completed_stages` / `per_stage_artifacts`

工具内置 `safe_mkdir` 兼容 WorkBuddy 沙箱误报 `EEXIST` 的行为（与 `wiki-creator/_root.safe_mkdir` 同源）。

## 维护协议

- 字段增删必须同步更新本文件 v 版本号与 `agents/_handoff_schema.md` 的引用
- `_state.json` 落到 `.harness-kb/`，与 `learnings.md` / `mode2-log.md` 同目录，便于项目级资产统一治理
- **不得**把 `_state.json` 提交进仓库——它是工作区运行时状态，跨机器无意义
