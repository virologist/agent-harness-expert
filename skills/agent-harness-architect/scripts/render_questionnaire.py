#!/usr/bin/env python3
"""按维度渲染需求澄清问卷骨架（纯模板变换，不做任何意图识别）。

哪个维度缺失由调用方（LLM）判断，脚本只负责把选定维度渲染成 md。

用法:
    python3 render_questionnaire.py --dims goal,success,oracle --project 支付助手 --out q.md
    python3 render_questionnaire.py --all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

DIMS = [
    ("goal", "目标与用途", "这个 agent / harness 是做什么的？一句话说清它要完成什么任务。",
     "目标决定后面六层里几乎每一层的设计方向。"),
    ("success", "成功标准", "做到什么程度算\"做对了\"？用什么客观指标衡量（准确 / 快 / 零误操作 / 可复现……）？",
     "这直接决定 V 层（评估接口）验证什么。"),
    ("oracle", "验收来源（oracle）", "凭什么判定达标？有没有现成的测试集 / 对照系统 / 权威数据源 / 人工抽检口径？没有的话，造一个的成本多大？",
     "测试与 oracle 的质量是 agent 能力的天花板——没有可信验收来源，V 层只能自评，等于循环论证。"),
    ("task", "任务结构", "任务是「固定流程」（步骤可枚举、每次一样）、「开放式探索」（需要试错判断），还是两者都有？",
     "决定 E 层用静态执行模式，还是需要动态编排。"),
    ("data", "数据 / 资源边界", "它能读写什么？数据源是什么（数据库 / 文件 / 线上 API）？只读还是可写？",
     "决定 T 层接什么、执行环境怎么隔离、L 层怎么拦。"),
    ("constraint", "硬约束", "有没有硬性约束？如安全（不能动生产数据）、可恢复（误操作能回滚）、成本、延迟、合规？",
     "约束是设计取舍的边界，违反约束的方案一律排除。"),
    ("user", "用户与场景", "谁用？什么环境（本地 / 服务器 / 团队协作）？单智能体还是多智能体？",
     "决定 P 的部署拓扑与编排模式，以及审批 / 权限的粒度。"),
    ("boundary", "边界（明确不做什么）", "明确**不**做什么？划清范围，避免 scope 蔓延。",
     "边界是设计的护栏，也是 L 层拒绝清单的来源。"),
    ("stack", "技术栈约束", "有没有技术栈偏好或限制？（语言、已有依赖、必须兼容的运行环境）",
     "设计文档要\"可直接编码\"，技术栈是编码的前提。"),
    ("model", "模型策略与成本",
     "① 对单次任务的延迟/成本敏感度如何？有没有总预算？② 任务里有多少\"封闭答案集、高频重复\"的窄决策（如分类/路由/门控）？"
     "③ 是否接受\"不同步骤用不同档位的模型\"（主推理用强模型、窄决策与简单子任务用快速低价模型）？④ 有无模型供应商/私有化部署约束？",
     "决定模型组合设计——任务-模型分派表、预算分配与级联升级条件都从这里来；措辞不预设多智能体，单智能体循环内分档同样适用。"),
    ("efficiency", "效率与体感",
     "① 用户能接受的端到端等待是多久？第一个字多久要出来（是否必须流式增量输出）？"
     "② 服务端有没有前缀缓存可用、你能否保证每轮前缀字节稳定（工具表顺序、序列化是否可固定）？"
     "③ 一轮里哪些步骤互不依赖可以并行、哪些必须串行？④ 要不要支持中途取消？取消时已经发生的写操作怎么处理？",
     "决定 C 层的前缀分区与序列化纪律、E 层的墙钟预算与并行度上限、是否需要流式与可中断；"
     "也决定预算表里哪部分是重算 token、哪部分是可命中的 cached token。"),
]

IDS = [d[0] for d in DIMS]


def render(project: str, dims: list) -> str:
    order = {d[0]: d for d in DIMS}
    lines = [
        f"# {project} 需求澄清问卷",
        "",
        "你可以用三种方式回答，任选其一：① 直接对话框回答（可简答）"
        " ② 在本 md 每题下方填写后整份发回 ③ 说\"你来做\"，我给参考答案 + 依据。",
        "没想好的题可以留空，我按默认假设补齐并标注\"可推翻\"。",
        "",
    ]
    for i, dim_id in enumerate(dims, start=1):
        dim_id = dim_id.strip()
        if dim_id not in order:
            raise SystemExit(f"未知维度: {dim_id}（可选: {', '.join(IDS)}）")
        _, title, question, why = order[dim_id]
        lines += [
            f"### Q{i}. {title}",
            f"- 问题：{question}",
            f"- 为什么问：{why}",
            "- 你的答案：",
            "",
        ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="渲染需求澄清问卷骨架")
    ap.add_argument("--dims", help=f"逗号分隔的维度 id，可选: {', '.join(IDS)}")
    ap.add_argument("--all", action="store_true", help="渲染全部 11 个维度")
    ap.add_argument("--project", default="<项目名>", help="项目名，写入问卷标题")
    ap.add_argument("--out", help="输出文件路径，缺省打印到 stdout")
    args = ap.parse_args()

    if args.all:
        dims = IDS
    elif args.dims:
        dims = [d for d in args.dims.split(",") if d.strip()]
    else:
        ap.error("须指定 --dims 或 --all")

    text = render(args.project, dims)
    if args.out:
        out = Path(args.out).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"已写入问卷: {out}（{len(dims)} 个维度）")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
