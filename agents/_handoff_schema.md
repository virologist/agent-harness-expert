# 回传信封 schema（v1）

每成员完成阶段产出后，按下表字段向主理人 SendMessage 回传，≤15 行自然语言即可但**必填字段不可缺**。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| stage | str | 是 | 阶段：P0 / P1 / P2 / P3 / P4 |
| status | enum | 是 | complete / partial / blocked / turns_exhausted |
| output_path | path | 是 | 落盘目录绝对路径 |
| summary | str | 是 | ≤15 行结构化摘要（保留各成员原有元素枚举） |
| open_items | list | 是 | 遗留/未决/待管家节点裁决条目 |
| evidence | list | 否 | 真实执行证据路径（命令+输出+退出码，参考 testing-basics §8.2） |
| blockers | list | 否 | status=blocked 时必填，说明卡在哪、要谁解 |
| turns_exhausted_at | str | 否 | status=turns_exhausted 时必填，标注「轮次耗尽，产出不完整」 |

字段值就嵌在 SendMessage 自然语言里按上述字段结构组织回传；主理人按字段逐项核验，缺字段则要求成员补齐再放行（v2 升级为 JSON envelope 时再改）。

## 维护协议

- 任何成员 MD 的「SendMessage 回传」节必须引用本文件路径
- 字段增删必须同步更新所有 4 成员 MD 的引用与本文件 v 版本号
- 撞限场景：status=turns_exhausted 时 `turns_exhausted_at` 必填，且 summary 头部必须显式标注「轮次耗尽，产出不完整」（与各成员 MD「撞限协议（内置）」节一致）
