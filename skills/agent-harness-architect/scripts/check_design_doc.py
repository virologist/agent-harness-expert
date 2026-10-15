#!/usr/bin/env python3
"""设计文档结构自检（schema 校验：已知结构 -> 确定结果）。

只报"缺什么"，不判断"该不该缺"——要不要补由 LLM/架构师决定。

退出码语义（默认即严格，门禁不做"假绿"）：
    0  无缺失项；或显式 --lenient（有问题也放行，仅作提示）
    1  存在任一缺失项（默认行为，无需加参数）
    --strict 保留为向后兼容开关，当前等同于默认行为。

检查面（**五项全部参与门禁判定**，任何一项不满足即默认退出码 1）：
    1. 15 个必需章节
    2. 9 个生产级必答项关键词 + §13 结论列是否真填
    3. 设计台账行
    4. 未填占位符 <...>
    5. H 框架六层必答设计问题覆盖 X/43（见 QUESTION_KEYWORDS）+ 分层结构是否完整

**43 问覆盖是"结构完整性启发式"，不是语义判断**：脚本只报"文档里没提到这个词"，
不报"答得好不好"。按本包「三件事分工宪法」，语义质量判定（答案是否成立、
是否自洽）归 LLM/架构师，脚本只做它能确定的字符串层面检查。

为避免"关键词堆砌即满分"，43 问匹配有三条硬约束（阈值依据见各自常量注释）：
    a) 限域：E 问只在 §4.1 段内找、T→§4.2、C→§4.3、S→§4.4、L→§4.5、V→§4.6；
       找不到对应分层段落 → 该层整层计为未覆盖，并报结构性问题（不静默全文匹配）。
    b) 最小答案长度：该层段落正文 ≥ MIN_SECTION_CHARS，且命中行 ≥ MIN_LINE_CHARS。
    c) 词边界：纯 ASCII 关键词（wal / state / jwt / sso / oidc 等）用 \b 匹配，
       避免 paywall / statement / Cornwall 这类误命中。

用法:
    python3 check_design_doc.py designs/支付助手-harness-design-v1.md
    python3 check_design_doc.py designs/xxx.md --template problem-solution
    python3 check_design_doc.py designs/xxx.md --lenient   # 只提示，不卡门禁

模板（v1.7.2 起多模板支持）：
    harness（默认，向后兼容）：15 标题 + §4.1-§4.6 限域 + 43 问门禁
    problem-solution：非 H 框架式设计文档（§N 问题/方案/推荐结构）。
        - 不强制 15 标题、不要求 §4.1-§4.6 限域、不查 43 问
        - 必含一级标题关键词之一（现状/痛点 / 方案 / 推荐 / 兼容性 / Backlog / 结论）
        - 保留 §13 必答项、占位符、设计台账检查（结构完整性不分模板）

WHY v1.7.2：
    v1.7.1 实证：真实样本 viral-evo-lab/P4_monitoring_design.md（§1 现状与痛点 / §2 候选方案 /
    §3 推荐架构 / §4 兼容性 / §5 Backlog / §6 结论）跑 harness 模板 → 4/43 覆盖 + exit 1，
    100% 不匹配 H 框架 15 标题 + §4.x 限域。本补丁加 problem-solution 模板承认这一类
    真实设计的存在合理性。
"""
import argparse
import re
from pathlib import Path

HEADINGS = [
    "需求规格", "架构范式 P", "技术栈选型", "六层设计", "模型组合与任务分派", "多 Agent 编排",
    "模块 / 目录结构", "关键接口签名", "核心数据结构", "配置文件格式",
    "层间交叉检查", "六层决策表", "生产级必答项", "参考架构图", "遗留问题与未知区",
]

# 生产级必答项（与 assets/design-doc.md §13 一致）+ 模型组合（§5）
# P3-1 加固：每条 MUST_ANSWER 项**限域到对应层号 §4.N 段**——除了"模型组合"跨层
# 归 §5 不限域外，其余 8 项必须出现在对应 §4.N 段才算覆盖。这是 P0-3c 收紧 43 问
# 限域的延伸：让 MUST_ANSWER 与 §4.1-§4.6 限域精神保持一致（关键词只在限域段算覆盖），
# 防止"在 §13 表格或 §0 概述里列一遍就 9/9 满分"的假绿。
#
# - MUST_ANSWER_LAYERS：label → 层号（None 表示不限域）
#   必须依据：references/h-framework.md 的 43 问归层 → 对应 §4.N
#     执行环境 → T（T3 工具执行位置）
#     错误回喂 → E（E4 失败回喂）
#     打转检测 → E（E5 打转检测）
#     记忆治理 → S（S5 记忆治理）
#     幂等      → S（S4 外部副作用幂等）
#     版本绑定  → S（S6 证据版本绑定）
#     评估者分离 → V（V3 评估者分离）
#     模型组合   → None（跨 E/T/C 三档，由 §5 模型组合与任务分派承载，限域意义不大）
#     前缀稳定  → C（C7 前缀稳定）
#
# - MUST_ANSWER_KEYWORDS：label → 限域段内允许命中的关键词列表（任一命中即覆盖）。
#   "错误回喂"给出 ["回喂", "失败回喂", "错误回喂"] 是因为 §4.1 E 段最自然的写法
#   是「失败回喂：错误作为观察结果回到上下文」——"错误回喂"作为整词往往只在 §13
#   表格里出现，但 §4.1 正文里命中"回喂"或"失败回喂"已足够语义覆盖。
MUST_ANSWER = [
    "执行环境", "错误回喂", "打转检测", "记忆治理", "幂等", "版本绑定", "评估者分离",
    "模型组合", "前缀稳定",
]
MUST_ANSWER_LAYERS: dict[str, str | None] = {
    "执行环境": "T",
    "错误回喂": "E",
    "打转检测": "E",
    "记忆治理": "S",
    "幂等": "S",
    "版本绑定": "S",
    "评估者分离": "V",
    "模型组合": None,  # 跨 E/T/C 三档，不限域（§5 承载）
    "前缀稳定": "C",
}
MUST_ANSWER_KEYWORDS: dict[str, list[str]] = {
    "执行环境": ["执行环境"],
    "错误回喂": ["回喂", "失败回喂", "错误回喂"],
    "打转检测": ["打转检测"],
    "记忆治理": ["记忆治理"],
    "幂等": ["幂等"],
    "版本绑定": ["版本绑定"],
    "评估者分离": ["评估者分离"],
    "模型组合": ["模型组合"],
    "前缀稳定": ["前缀稳定"],
}

# 「可编码三门槛」（类型完整 / API 真实 / 标准可达）的唯一定义处是
# references/production-checklist.md。三门槛判定的是**内容质量**（类型有没有定义、
# API 是否真实、标准能否验证），属于语义判断，按三件事分工宪法归LLM，不做脚本化。
# 脚本只做它能确定的事：§13 每一行是否真的填了结论。
GATE_POINTER = "类型完整 / API 真实 / 标准可达（唯一定义处：references/production-checklist.md）"

# §13 生产级必答项的编号行，检测「表还在但结论列全空」这种结构性缺失
_ANSWER_ROW = re.compile(r"^\|\s*(\d+)\s*\|([^|]*)\|([^|]*)\|")

# ---------------------------------------------------------------------------
# 模板（v1.7.2 起多模板支持）
#
# 结构完整性检查（所有模板共用）：§13 必答项、占位符、设计台账
# 模板特殊检查（仅 harness）：15 标题、§4.x 限域、MUST_ANSWER 限域、43 问门禁
# 模板特殊检查（仅 problem-solution）：一级标题关键词 OR 命中
#
# cfg["headings"]:           强制的一级标题列表（harness 15 个，problem-solution []）
# cfg["must_answer_layers"]: MUST_ANSWER 限域映射（harness 按层号，problem-solution {} → 全 None）
# cfg["check_43q"]:          是否启用 43 问门禁
# cfg["require_layer_sections"]: 是否要求 §4.1-§4.6 存在（harness True）
# cfg["required_section_keywords"]: 必含的一级标题关键词列表（problem-solution 6 个关键词 OR 命中）
# ---------------------------------------------------------------------------
TEMPLATES: dict[str, dict] = {
    "harness": {
        "headings": HEADINGS,
        "must_answer_layers": MUST_ANSWER_LAYERS,
        "check_43q": True,
        "require_layer_sections": True,
        # harness 模板下不强制一级标题关键词（15 个标题本身已涵盖结构）
        "required_section_keywords": None,
    },
    "problem-solution": {
        # 不强制 15 标题（真实设计如 viral-evo-lab/P4 用的就是 §1-§6 六段式）
        "headings": [],
        # MUST_ANSWER 全部不限域（problem-solution 模板没有 §4.1-§4.6 分层）
        "must_answer_layers": {},
        # 43 问门禁仅对 H 框架式设计生效（problem-solution 没有 §4.1-§4.6）
        "check_43q": False,
        # 不要求六层分层段（结构完整性归 §13 + 占位符 + 台账三件套）
        "require_layer_sections": False,
        # 必含一级标题关键词之一（OR 命中）：覆盖真实 P4 文档的「§1 现状与痛点 / §2 候选方案 /
        # §3 推荐架构 / §4 兼容性 / §5 Backlog / §6 结论」结构。6 关键词至少命中 1 即视为结构合法。
        # 用具体短语（如「候选方案」「推荐架构」而非单字「方案」「推荐」）避免假命中：
        # - design_headings_only.md 在「§13 八个必答项也都填了结论」一句里命中单字「结论」，
        #   若用「结论」作关键词会误判该 H 框架式负样本通过 problem-solution 门禁。
        "required_section_keywords": [
            "现状与痛点",  # §1 现状与痛点
            "候选方案",    # §2 候选方案
            "推荐架构",    # §3 推荐架构
            "兼容性",      # §4 与既有机制的兼容性
            "Backlog",     # §5 Backlog（实现项清单，英文术语跨语言）
            "建议排期",    # §6 结论（避免用单字「结论」误命中）
        ],
    },
}
#
# 权威源：references/h-framework.md「二、六层详解」每层的「必答设计问题」列表。
# 分布：E 9 / T 7 / C 8 / S 6 / L 6 / V 7 = 43 问。
#   （总定义节的「模型组合」6 问不在此表——它们由 §5 模型组合与任务分派章节承载，
#     归 MUST_ANSWER 的"模型组合"与 HEADINGS 检查，避免同一问两处计数。）
#
# 每条 = (编号, 人类可读标签, [关键词...])；关键词命中**其一**即视为该问已覆盖。
# 匹配在 _strip_fenced() 去围栏后的正文上做，大小写不敏感。
#
# 【这是启发式，不是语义判定】关键词取每问里最不可替代的术语；脚本只能证明
# "文档提到了这个概念"，无法证明"这个概念被答对了"。后者归 LLM（三件事分工宪法）。
# ---------------------------------------------------------------------------
QUESTION_KEYWORDS: dict[str, list] = {
    "E": [
        ("E1", "终止条件归属", ["终止条件"]),
        ("E2", "防跑飞三保险", ["轮次上限", "token 预算", "每节点超时"]),
        ("E3", "静态模式 vs 动态脚本", ["静态模式", "动态脚本"]),
        ("E4", "失败回喂", ["回喂", "分类恢复"]),
        ("E5", "打转检测", ["打转", "参数指纹"]),
        ("E6", "循环内分档", ["档位", "分派"]),
        ("E7", "策略选择器", ["策略选择器"]),
        ("E8", "墙钟预算与并行", ["墙钟", "并行"]),
        ("E9", "流式与可中断", ["流式", "可中断"]),
    ],
    "T": [
        ("T1", "工具接入与接口标准化", ["工具接入", "接入方式", "接口标准化"]),
        ("T2", "按需筛选子集", ["按需筛选", "工具子集"]),
        ("T3", "工具执行位置", ["执行环境", "沙箱"]),
        ("T4", "凭证不进执行环境", ["凭证"]),
        ("T5", "注册≠披露≠授权", ["披露", "执行授权"]),
        ("T6", "模型组件接入形态", ["接入形态", "降级链"]),
        ("T7", "披露序列稳定", ["披露序列", "披露顺序"]),
    ],
    "C": [
        ("C1", "窗口预算分配", ["窗口预算", "预算分配"]),
        ("C2", "压缩与摘要时机", ["压缩", "摘要"]),
        ("C3", "噪音下沉", ["噪音下沉", "干净上下文"]),
        ("C4", "每轮重新组装", ["重新组装", "组装策略"]),
        ("C5", "外部内容消毒", ["消毒"]),
        ("C6", "决策型模型 state 复用", ["state", "复用"]),
        ("C7", "前缀稳定", ["前缀稳定", "稳定前缀"]),
        ("C8", "重写失效预算", ["失效预算", "重写"]),
    ],
    "S": [
        ("S1", "存储结构与写入治理", ["存储结构", "状态结构"]),
        ("S2", "失败后重新加载", ["重新加载", "可恢复"]),
        ("S3", "并发写", ["并发写", "wal", "连接池"]),
        ("S4", "外部副作用幂等", ["幂等"]),
        ("S5", "记忆治理", ["记忆治理"]),
        ("S6", "证据版本绑定", ["版本绑定"]),
    ],
    "L": [
        ("L1", "拦截点", ["拦截"]),
        ("L2", "拦截不可绕过", ["绕过"]),
        ("L3", "鉴权协议", ["jwt", "sso", "oidc", "鉴权协议"]),
        ("L4", "人在回路四档", ["人在回路"]),
        ("L5", "高危纵深防御", ["纵深"]),
        ("L6", "快筛阈值与放行率", ["放行率", "阈值"]),
    ],
    "V": [
        ("V1", "独立验证", ["独立验证"]),
        ("V2", "可量化可复现", ["可量化", "可复现"]),
        ("V3", "评估者分离", ["评估者分离", "独立上下文"]),
        ("V4", "显式标准与迭代预算", ["迭代预算"]),
        ("V5", "回执≠业务事实", ["回执", "业务事实"]),
        ("V6", "评测环境可比", ["评测环境", "可比", "绕过任务"]),
        ("V7", "验证强度阶梯", ["验证强度", "强度阶梯"]),
    ],
}

# 缺失清单最多列多少条（防刷屏）
MAX_UNCOVERED_SHOWN = 15


def total_questions() -> int:
    return sum(len(v) for v in QUESTION_KEYWORDS.values())


def _compile_keyword(kw: str):
    """纯 ASCII 关键词（wal / state / jwt / sso / oidc…）用词边界匹配。

    这些词只有 3-5 个字符，子串匹配会被 paywall / statement / Cornwall 之类的
    普通英文词误命中；中文关键词不存在这个问题，直接子串匹配。
    """
    if kw.isascii():
        return re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
    return None


_KEYWORD_RX = {
    kw: _compile_keyword(kw)
    for _layer, questions in QUESTION_KEYWORDS.items()
    for _qid, _label, keywords in questions
    for kw in keywords
}

# ---------------------------------------------------------------------------
# 43 问匹配的三条硬约束（防止"把关键词堆一排"就能拿满分）
# ---------------------------------------------------------------------------

# 层 → §4.N 段号（与 assets/design-doc.md §4 一致）
LAYER_SECTION = {"E": 1, "T": 2, "C": 3, "S": 4, "L": 5, "V": 6}

# (a) 分层段落标题：`## 4.1 ...` / `### 4.1 ...` 两种层级都认
_SEC_HEADING_RE = re.compile(r"^(#{2,4})\s*4\.(\d)\b.*$", re.MULTILINE)
_ANY_HEADING_RE = re.compile(r"^(#{1,6})\s", re.MULTILINE)

# (b) 最小答案长度
#   MIN_SECTION_CHARS=200：一层正文不足 200 字符 ≈ 三句话都不到，等于该层没作答。
#   依据：两份"按模板认真填"的正样本（tests/fixtures/design_full.md、
#   design_from_template.md）六层段落实测均在 500–900 字符，留 2.5 倍以上余量；
#   而"每层一句空话 + 关键词平铺"的文档每层只有 100 字符上下，正好被挡在门外。
#   MIN_LINE_CHARS=20：一行 20 字符 ≈ 一个名词短语，挡"每行只贴 1-2 个关键词不展开"的
#   极端凑数写法；自然陈述句（30-60 字符）和表格行（可逐行达到）不受影响。
#   已知代价：用极短行逐项作答的文档会被判未覆盖——这是刻意的严格，
#   改写成陈述句即可，或用 --lenient 放行。
MIN_SECTION_CHARS = 200
MIN_LINE_CHARS = 20


def split_layer_sections(body: str) -> dict:
    """按 `4.N` 标题切出六层段落，返回 {段号: 段落正文}。

    段落边界 = 下一个层级 ≤ 当前标题层级的标题（同级 `### 4.2` 或上级 `## 5.` 都算）。
    """
    heads = [
        (m.end(), len(m.group(1)), int(m.group(2)))
        for m in _SEC_HEADING_RE.finditer(body)
    ]
    sections = {}
    for i, (start, level, num) in enumerate(heads):
        end = len(body)
        for m in _ANY_HEADING_RE.finditer(body, start):
            if len(m.group(1)) <= level:
                end = m.start()
                break
        # 同名段号重复出现时保留内容更长的一段（防目录/摘要页抢跑）
        if len(body[start:end].strip()) >= len(sections.get(num, "").strip()):
            sections[num] = body[start:end]
    return sections


def _keyword_hit(keyword: str, lines: list) -> bool:
    """关键词是否在某一行命中，且该行达到最小答案长度。"""
    rx = _KEYWORD_RX.get(keyword)
    for line in lines:
        hit = bool(rx.search(line)) if rx is not None else keyword.lower() in line.lower()
        if hit and len(line.strip()) >= MIN_LINE_CHARS:
            return True
    return False


def find_uncovered(body: str, cfg: dict) -> tuple:
    """返回 (未覆盖问题列表, 结构性问题列表)。

    只判**有没有按层写到、写够长度**（结构完整性），不判**答得好不好**（语义质量）。
    后者按三件事分工宪法归 LLM，脚本不做规则匹配。

    v1.7.2 多模板扩展：cfg["check_43q"] = False 时（如 problem-solution 模板），
    43 问门禁不启用 → 返回 ([], [])。problem-solution 是「问题-方案-推荐」结构，
    没有 H 框架 §4.1-§4.6 分层，43 问限域无从谈起；模板存在意义是承认这一类
    真实设计有结构合理性，由 §13 + 占位符 + 台账三件套兜底。
    """
    if not cfg.get("check_43q", True):
        # problem-solution 等模板：43 问门禁不启用
        return [], []
    sections = split_layer_sections(body)
    structural = []

    if not sections:
        # 找不到任何 4.1–4.6 标题：不静默降级为全文匹配（那等于没做限域），
        # 而是明确记为结构性问题，同时退化为全文匹配以便给出覆盖数参考。
        structural.append(
            "缺六层分层结构：未找到任何 `4.1`–`4.6` 标题，43 问无法按层定位"
            "（已退化为全文匹配，仍计为缺失项）"
        )
        sections = {n: body for n in LAYER_SECTION.values()}

    uncovered = []
    for layer, questions in QUESTION_KEYWORDS.items():
        num = LAYER_SECTION[layer]
        if num not in sections:
            structural.append(f"缺分层段落: §4.{num}（{layer} 层）")
            uncovered.extend(f"{qid} {label}" for qid, label, _kw in questions)
            continue
        sec = sections[num]
        if len(sec.strip()) < MIN_SECTION_CHARS:
            # 该层正文过少 —— 整层视为未作答（挡掉"每层一句空话 + 关键词平铺"）
            uncovered.extend(f"{qid} {label}" for qid, label, _kw in questions)
            continue
        lines = sec.splitlines()
        for qid, label, keywords in questions:
            if not any(_keyword_hit(k, lines) for k in keywords):
                uncovered.append(f"{qid} {label}")
    return uncovered, structural


def find_missing_must_answer(text: str, body: str, sections: dict, cfg: dict) -> tuple[list[str], list[str]]:
    """P3-1 加固：MUST_ANSWER 按 cfg["must_answer_layers"] 限域。

    返回 (missing_labels, structural_msgs)：
      - missing_labels：限域段存在但段内未找到任一关键词 / 限域段缺失且全文未找到
        任一关键词 的 label 列表；
      - structural_msgs：限域段缺失时退回全文档匹配的结构性提示（不阻断，
        只报缺指针——这是 v1.6.0 已知的"§4.4 S 段被吞"的过渡态）。

    v1.7.2 多模板扩展：
      - harness 模板 → cfg["must_answer_layers"] = MUST_ANSWER_LAYERS（按 §4.N 限域）
      - problem-solution 模板 → cfg["must_answer_layers"] = {} → 所有 label 视为
        不限域（layer = None），退化为全文档匹配。problem-solution 没有 §4.1-§4.6，
        MUST_ANSWER 限域无从谈起；保留 MUST_ANSWER 检查是为了「即使是非 H 框架式设计，
        也至少要在文档里提到执行环境 / 错误回喂 / 打转检测 / ... 这 9 个核心概念」。
        这是 LLM/架构师能直接读到的「最小结构性提示」，比纯章节齐全度更扎实。

    限域规则与例外（与 43 问门禁同精神）：
      - 有限域段 → 关键词必须在该 §4.N 段内命中（任一关键词命中即覆盖）；
      - 限域段缺失 → 退回全文档匹配并报结构性问题（不静默全文档化）；
      - 「模型组合」层号 None → 始终全文档匹配（跨 E/T/C，限域意义不大）。

    【这是结构面启发式】关键词命中只证明"该层提到了这个概念"，
    不能证明"答得好不好"。后者归 LLM（三件事分工宪法）。
    """
    missing: list[str] = []
    structural: list[str] = []
    layers_map: dict = cfg.get("must_answer_layers") or {}
    for label, kws in MUST_ANSWER_KEYWORDS.items():
        layer = layers_map.get(label)
        if layer is None:
            # 跨层不限域（如"模型组合"归 §5），全文档匹配
            pool = body
            tag = "全文档"
        else:
            num = LAYER_SECTION[layer]
            # 先固定 tag，再决定 pool——避免限域段缺失分支先于结构面段写 f-string
            tag = f"§4.{num}（{layer} 层）"
            if num in sections:
                pool = sections[num]
            else:
                # 限域段缺失 → 退回全文档匹配并报结构性问题
                structural.append(
                    f"MUST_ANSWER「{label}」所属 {tag} 段落缺失，"
                    f"已退回全文档匹配"
                )
                pool = body
        if not any(kw in pool for kw in kws):
            missing.append(label)
    return missing, structural


# 已被文档规范占用的合法记号：出现这些形态时不算"未填占位符"
#   - HTML/SVG 标签：<div> <T> <name> <your-key>
#   - 泛型 / 类型参数：List<String>、Dict<K, V>、Promise<T>
#   - 比较与数学：a < b、x <= 1、n < 10
_ALLOWED_TAG = re.compile(
    r"^<[A-Za-z_][A-Za-z0-9_.:\-]*(?:\s*/?)?>$"      # <div> <T> <my-key> </span>
)
_TOLDF_SLOT = re.compile(r"^<[^<>\n]+>$")
# `<` 左侧紧邻这些字符时，几乎必然是比较运算或泛型（a<b、List<T>、x<=1）
_IDENT_CHAR_BEFORE = re.compile(r"[A-Za-z0-9_)\]]$")
# 形似标签但实为占位符的常见缩写（TBD / TODO / FIXME / XXX）
_TODO_LIKE = re.compile(r"^<(?:TBD|TODO|FIXME|XXX|N/A|N/T)>$", re.IGNORECASE)

# 「短尖括号」的长度上限。短的一律算未填占位符（模板提示词就是这个量级）。
# 超过上限的**不再无条件放行**——见 _is_placeholder_token 的双条件判定。
MAX_PLACEHOLDER_CHARS = 60


def _token_has_question_keyword(tok: str) -> bool:
    """尖括号内容里是否含 43 问关键词。

    用途：模板提示词 = 门禁关键词。若把多条提示词合并成一条长尖括号（>60 字符），
    长度条件会失效，"留着不填"就白拿 43/43。含关键词的长尖括号一律仍算未填。
    """
    for kw, rx in _KEYWORD_RX.items():
        if rx is not None:
            if rx.search(tok):
                return True
        elif kw.lower() in tok.lower():
            return True
    return False


def _is_placeholder_token(tok: str, line_prefix: str) -> bool:
    """判断单个 <...> 记号是否为未填占位符。

    line_prefix 是该记号在同一行左侧的原文，用于识别比较运算 / 泛型场景。

    判定顺序：
      1. 合法标签形态 / 比较与泛型 → 一定不是占位符（先排除，避免误伤正文）
      2. TBD / TODO 之类 → 一定是
      3. 短尖括号（≤ MAX_PLACEHOLDER_CHARS）→ 是
      4. 长尖括号但含 43 问关键词 → 仍是未填提示词（防止合并提示词逃逸）
      5. 其余长尖括号（如长 URL、长标签）→ 不是
    """
    if not _TOLDF_SLOT.match(tok):
        return False
    if _ALLOWED_TAG.match(tok):
        return False
    # 比较运算或泛型：a < b、x <= 1、List<String>
    if _IDENT_CHAR_BEFORE.search(line_prefix):
        return False
    if _TODO_LIKE.match(tok):
        return True
    if len(tok) - 2 <= MAX_PLACEHOLDER_CHARS:
        return True
    return _token_has_question_keyword(tok)


def find_placeholders(body: str) -> list:
    """返回正文中疑似未填的占位符列表（已排除代码围栏内的合法尖括号）。

    判定策略：逐个 <...> 记号看**长度、内容、行内左侧上下文**三者——
    左侧紧邻标识符字符 → 判为比较运算/泛型，放行；
    记号本身是合法标签形态 → 放行；
    短尖括号（模板提示词量级）→ 判为未填占位符；
    长尖括号但含 43 问关键词 → 同样判为未填（合并提示词不构成免费通行证）。
    """
    found = []
    for line in body.splitlines():
        for m in re.finditer(r"<[^<>\n]+>", line):
            if _is_placeholder_token(m.group(0), line[: m.start()]):
                found.append(m.group(0))
    return found


def _strip_fenced(text: str) -> str:
    """去掉 ``` 围栏代码块内容（占位符检测不看代码块内合法尖括号）。"""
    out, in_fence = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def find_unanswered(body: str) -> list:
    """返回 §13 生产级必答项里「有编号但结论列为空」的条目。

    只判**结构**（表还在、行还在、结论没写），不判内容质量——
    「结论写得够不够」归LLM，按三件事分工宪法不做规则匹配。
    """
    unanswered = []
    for line in body.splitlines():
        m = _ANSWER_ROW.match(line.strip())
        if not m:
            continue
        num, item, conclusion = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        # 跳过表头行与分隔行（表头形如| # | 必答项 | 结论 |）
        if not num.isdigit():
            continue
        if not conclusion:
            unanswered.append(f"§13 第 {num} 项「{item or '未命名'}」未填结论")
    return unanswered


def find_missing_required_section_keywords(text: str, cfg: dict) -> list[str]:
    """problem-solution 模板专用：必含一级标题关键词之一（OR 命中）。

    返回缺失的关键词列表（要求至少 1 个命中，0 命中则全列）。harness 模板下
    cfg["required_section_keywords"] = None → 返回 []（harness 已有 15 标题硬约束）。
    """
    kws = cfg.get("required_section_keywords")
    if not kws:
        return []
    if any(kw in text for kw in kws):
        return []
    return list(kws)


def check(path: Path, template: str = "harness") -> tuple:
    """v1.7.2 起接受 template 参数。返回顺序保持向后兼容（harness 模板的
    返回值与 v1.7.1 完全一致，新增字段以「(..., template_hits)」形式追加）。
    """
    if template not in TEMPLATES:
        raise SystemExit(
            f"未知模板: {template!r}（可用: {', '.join(TEMPLATES.keys())}）"
        )
    if not path.is_file():
        raise SystemExit(f"文件不存在: {path}")
    text = path.read_text(encoding="utf-8")
    cfg = TEMPLATES[template]

    headings = cfg["headings"]
    missing_h = [h for h in headings if h not in text]
    has_ledger = "设计台账" in text
    body = _strip_fenced(text)
    # problem-solution 模板下不切六层段（也用不到），但 sections 还是建一份供 MUST_ANSWER fallback
    sections = split_layer_sections(body) if cfg.get("require_layer_sections") else {}
    # P3-1 加固：MUST_ANSWER 限域到 §4.N 段（harness）；problem-solution 全 None → 全文档匹配
    missing_m, ma_structural = find_missing_must_answer(text, body, sections, cfg)
    placeholders = find_placeholders(body)
    unanswered = find_unanswered(body)
    uncovered, fc_structural = find_uncovered(body, cfg)
    # problem-solution 模板特殊：必含一级标题关键词
    missing_section_kws = find_missing_required_section_keywords(text, cfg)
    # 合并两路结构性提示：43 问分层结构问题 + MUST_ANSWER 限域段缺失告警
    structural = fc_structural + ma_structural
    return (
        missing_h, missing_m, has_ledger, unanswered,
        placeholders, uncovered, structural, missing_section_kws,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="设计文档结构自检（默认严格：有缺失即退出码 1）")
    ap.add_argument("doc", help="设计文档路径")
    ap.add_argument("--template", default="harness", choices=list(TEMPLATES.keys()),
                    help="设计文档模板（harness=默认/H 框架式 / "
                         "problem-solution=§N 问题-方案-推荐式）。v1.7.2 起多模板支持。")
    ap.add_argument("--strict", action="store_true",
                    help="存在任一项缺失即以退出码 1 结束（向后兼容；当前等同默认行为）")
    ap.add_argument("--lenient", action="store_true",
                    help="宽松模式：存在缺失项也返回 0，仅作提示不卡门禁")
    args = ap.parse_args()

    result = check(Path(args.doc).expanduser().resolve(), template=args.template)
    missing_h, missing_m, has_ledger, unanswered, placeholders, uncovered, structural, missing_section_kws = result

    cfg = TEMPLATES[args.template]
    headings = cfg["headings"]

    print(f"检查对象: {Path(args.doc).resolve()}")
    print(f"  模板: {args.template}")
    if headings:
        print(f"  章节齐全度: {len(headings) - len(missing_h)}/{len(headings)}")
        if missing_h:
            print(f"    缺章节: {', '.join(missing_h)}")
    print(f"  生产级必答项: {len(MUST_ANSWER) - len(missing_m)}/{len(MUST_ANSWER)}")
    if missing_m:
        print(f"    未出现: {', '.join(missing_m)}")
    if unanswered:
        print(f"  §13 必答项结论空缺: {len(unanswered)} 处")
        for u in unanswered:
            print(f"    - {u}")
    else:
        print("  §13 必答项结论空缺: 无")
    print(f"  设计台账行: {'有' if has_ledger else '缺'}")
    # 去重保序，最多列 10 个，避免刷屏
    uniq = list(dict.fromkeys(placeholders))
    print(f"  未填占位符 <...>: {'有，需补写 ' + str(len(uniq)) + ' 处 → ' + ', '.join(uniq[:10]) if uniq else '无'}")
    if cfg.get("check_43q", True):
        total = total_questions()
        print(f"  六层必答问题覆盖: {total - len(uncovered)}/{total}")
        if uncovered:
            shown = ", ".join(uncovered[:MAX_UNCOVERED_SHOWN])
            more = f" …等共 {len(uncovered)} 项" if len(uncovered) > MAX_UNCOVERED_SHOWN else ""
            print(f"    未覆盖: {shown}{more}")
    else:
        # problem-solution 模板：43 问门禁未启用（明文告知，便于审计）
        total = total_questions()
        print(f"  六层必答问题覆盖: 未启用（{args.template} 模板不强求 H 框架 §4.1-§4.6 分层）")
    if missing_section_kws:
        # problem-solution 模板专用：6 关键词至少命中 1
        print(f"  一级标题关键词（{args.template} 模板）: 缺")
        print(f"    未命中: {', '.join(missing_section_kws)}")
    if structural:
        print(f"  分层结构问题: {len(structural)} 项")
        for s in structural:
            print(f"    - {s}")
    print(f"  语义项（脚本不判，需你自查）: {GATE_POINTER}")

    # problems 判定：按模板分桶
    #   harness（默认）：v1.7.1 七项全过（missing_h, missing_m, unanswered, has_ledger,
    #                  uncovered, placeholders, structural）—— 与 v1.7.1 完全一致。
    #   problem-solution：仅「6 关键词命中 + 占位符 + §13 结论空缺」三项参与门禁。
    #     MUST_ANSWER / 台账 / 43 问门禁 / 15 标题 / §4.x 限域 在 problem-solution
    #     模板下**保留检查但不计门禁**——它们是 H 框架专属约束，对「问题-方案-推荐」
    #     结构的设计文档不适用。结构完整性（占位符 / §13）仍生效以确保语义质量下限。
    if args.template == "harness":
        problems = bool(
            missing_h or missing_m or unanswered or not has_ledger
            or uncovered or placeholders or structural
        )
    else:
        problems = bool(
            placeholders or unanswered or missing_section_kws
        )
    if not problems:
        print("结论: 结构完整")
        return 0
    print("结论: 存在缺失项，需人工判断是否补齐")
    if args.lenient:
        if args.strict:
            print("（同时给了 --strict 与 --lenient：以 --lenient 为准，退出码 0）")
        else:
            print("（--lenient：已按宽松模式放行，退出码 0；门禁须去掉本参数）")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
