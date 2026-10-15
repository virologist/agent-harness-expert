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
    python3 check_design_doc.py designs/xxx.md --lenient   # 只提示，不卡门禁
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
MUST_ANSWER = [
    "执行环境", "错误回喂", "打转检测", "记忆治理", "幂等", "版本绑定", "评估者分离",
    "模型组合", "前缀稳定",
]

# 「可编码三门槛」（类型完整 / API 真实 / 标准可达）的唯一定义处是
# references/production-checklist.md。三门槛判定的是**内容质量**（类型有没有定义、
# API 是否真实、标准能否验证），属于语义判断，按三件事分工宪法归LLM，不做脚本化。
# 脚本只做它能确定的事：§13 每一行是否真的填了结论。
GATE_POINTER = "类型完整 / API 真实 / 标准可达（唯一定义处：references/production-checklist.md）"

# §13 生产级必答项的编号行，检测「表还在但结论列全空」这种结构性缺失
_ANSWER_ROW = re.compile(r"^\|\s*(\d+)\s*\|([^|]*)\|([^|]*)\|")

# ---------------------------------------------------------------------------
# H 框架六层必答设计问题（43 问）→ 可检测关键词
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


def find_uncovered(body: str) -> tuple:
    """返回 (未覆盖问题列表, 结构性问题列表)。

    只判**有没有按层写到、写够长度**（结构完整性），不判**答得好不好**（语义质量）。
    后者按三件事分工宪法归 LLM，脚本不做规则匹配。
    """
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


def check(path: Path) -> tuple:
    if not path.is_file():
        raise SystemExit(f"文件不存在: {path}")
    text = path.read_text(encoding="utf-8")

    missing_h = [h for h in HEADINGS if h not in text]
    missing_m = [m for m in MUST_ANSWER if m not in text]
    has_ledger = "设计台账" in text
    body = _strip_fenced(text)
    placeholders = find_placeholders(body)
    unanswered = find_unanswered(body)
    uncovered, structural = find_uncovered(body)
    return missing_h, missing_m, has_ledger, unanswered, placeholders, uncovered, structural


def main() -> int:
    ap = argparse.ArgumentParser(description="设计文档结构自检（默认严格：有缺失即退出码 1）")
    ap.add_argument("doc", help="设计文档路径")
    ap.add_argument("--strict", action="store_true",
                    help="存在任一项缺失即以退出码 1 结束（向后兼容；当前等同默认行为）")
    ap.add_argument("--lenient", action="store_true",
                    help="宽松模式：存在缺失项也返回 0，仅作提示不卡门禁")
    args = ap.parse_args()

    missing_h, missing_m, has_ledger, unanswered, placeholders, uncovered, structural = check(
        Path(args.doc).expanduser().resolve()
    )

    print(f"检查对象: {Path(args.doc).resolve()}")
    print(f"  章节齐全度: {len(HEADINGS) - len(missing_h)}/{len(HEADINGS)}")
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
    total = total_questions()
    print(f"  六层必答问题覆盖: {total - len(uncovered)}/{total}")
    if uncovered:
        shown = ", ".join(uncovered[:MAX_UNCOVERED_SHOWN])
        more = f" …等共 {len(uncovered)} 项" if len(uncovered) > MAX_UNCOVERED_SHOWN else ""
        print(f"    未覆盖: {shown}{more}")
    if structural:
        print(f"  分层结构问题: {len(structural)} 项")
        for s in structural:
            print(f"    - {s}")
    print(f"  语义项（脚本不判，需你自查）: {GATE_POINTER}")

    problems = bool(
        missing_h or missing_m or unanswered or not has_ledger
        or uncovered or placeholders or structural
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
