"""check_design_doc.py 冒烟测试（退出码语义 + 43 问覆盖）。

覆盖：完整文档 / 缺章节 / §13 结论空 / 占位符 / --lenient / --strict 兼容 /
43 问正负样本 / 文件不存在。
"""
from __future__ import annotations

import importlib.util
import re

from _harness import (
    CHECK_DOC,
    DESIGN_TEMPLATE,
    FIXTURES,
    Workspace,
    contains,
    eq,
    exit_code,
    is_true,
    run,
)

FULL = FIXTURES / "design_full.md"
FROM_TEMPLATE = FIXTURES / "design_from_template.md"
MISSING_SECTIONS = FIXTURES / "design_missing_sections.md"
EMPTY_CONCLUSIONS = FIXTURES / "design_empty_conclusions.md"
PLACEHOLDER = FIXTURES / "design_placeholder.md"
HEADINGS_ONLY = FIXTURES / "design_headings_only.md"

_COVERAGE_RE = re.compile(r"六层必答问题覆盖:\s*(\d+)/(\d+)")


def _coverage(proc) -> tuple[int, int]:
    m = _COVERAGE_RE.search(proc.stdout)
    is_true(m is not None, f"输出中未找到「六层必答问题覆盖: X/43」行\n{proc.stdout}")
    return int(m.group(1)), int(m.group(2))


def test_complete_doc_exit_zero():
    proc = run(CHECK_DOC, [FULL])
    exit_code(proc, 0, "完整设计文档应通过")
    contains(proc.stdout, "结论: 结构完整", "完整文档结论")
    contains(proc.stdout, "章节齐全度: 15/15", "完整文档章节齐全度")


def test_missing_sections_exit_one():
    proc = run(CHECK_DOC, [MISSING_SECTIONS])
    exit_code(proc, 1, "缺章节应默认返回 1")
    contains(proc.stdout, "缺章节", "缺章节提示")
    contains(proc.stdout, "结论: 存在缺失项", "缺章节结论行")


def test_empty_conclusions_exit_one():
    proc = run(CHECK_DOC, [EMPTY_CONCLUSIONS])
    exit_code(proc, 1, "§13 结论列空应返回 1")
    contains(proc.stdout, "§13 必答项结论空缺: 8 处", "§13 空缺计数")
    contains(proc.stdout, "第 1 项", "§13 第 1 项应被点名")


def test_placeholder_detected_exit_one():
    proc = run(CHECK_DOC, [PLACEHOLDER])
    exit_code(proc, 1, "存在未填占位符应返回 1")
    contains(proc.stdout, "未填占位符 <...>: 有", "占位符提示")
    contains(proc.stdout, "<待填>", "具体占位符应被列出")


def test_lenient_returns_zero():
    proc = run(CHECK_DOC, [MISSING_SECTIONS, "--lenient"])
    exit_code(proc, 0, "--lenient 应放行（返回 0）")
    contains(proc.stdout, "--lenient", "宽松模式说明行")
    contains(proc.stdout, "结论: 存在缺失项", "宽松模式仍需打印问题结论")


def test_strict_flag_backward_compatible():
    """旧调用方传 --strict 时期望"有问题→1"，默认严格后仍满足。"""
    proc = run(CHECK_DOC, [MISSING_SECTIONS, "--strict"])
    exit_code(proc, 1, "--strict 向后兼容：有问题仍返回 1")
    proc_ok = run(CHECK_DOC, [FULL, "--strict"])
    exit_code(proc_ok, 0, "--strict 下完整文档仍返回 0")


def test_43q_positive_full_coverage():
    proc = run(CHECK_DOC, [FULL])
    covered, total = _coverage(proc)
    eq(total, 43, "43 问总数")
    eq(covered, 43, "正样本应 43/43 覆盖")
    exit_code(proc, 0, "43 问全覆盖文档应通过")


def test_43q_negative_headings_only():
    """标题齐全但六层问题全缺 —— 修复前的假绿场景，必须返回 1。"""
    proc = run(CHECK_DOC, [HEADINGS_ONLY])
    exit_code(proc, 1, "43 问大面积缺失应返回 1")
    covered, total = _coverage(proc)
    eq(total, 43, "43 问总数")
    is_true(covered <= 15, f"负样本覆盖数应显著低于 43，实际 {covered}/43")
    contains(proc.stdout, "未覆盖:", "应列出未覆盖问题清单")


def test_43q_gate_is_additive_not_replacing():
    """43 问检查是叠加项：原有检查（台账 / 占位符 / §13）仍在工作。

    P3-1 加固：MUST_ANSWER 也被限域到 §4.N 段——HEADINGS_ONLY 只有「模型组合」
    在 §5 标题里不限域命中，其余 8 项都必须出现在 §4.1-§4.6 段才覆盖。
    因此此 fixture 的「生产级必答项」在新规则下从 9/9 收紧到 1/9。
    """
    proc = run(CHECK_DOC, [HEADINGS_ONLY])
    contains(proc.stdout, "设计台账行: 有", "台账检查仍执行")
    contains(proc.stdout, "§13 必答项结论空缺: 无", "§13 检查仍执行")
    contains(proc.stdout, "生产级必答项: 1/9", "必答项检查仍执行（P3-1 限域后 HEADINGS_ONLY 应为 1/9）")


def _load_gate_module():
    """按路径加载 check_design_doc.py，直接读取门禁里的 QUESTION_KEYWORDS 真值。"""
    spec = importlib.util.spec_from_file_location("check_design_doc_gate", CHECK_DOC)
    if spec is None or spec.loader is None:
        raise AssertionError("无法加载 check_design_doc.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _template_layer_sections() -> dict[str, str]:
    """从 assets/design-doc.md 里切出 §4.1–4.6 六个层段落。"""
    text = DESIGN_TEMPLATE.read_text(encoding="utf-8")
    bounds = [
        "### 4.1 E 执行循环", "### 4.2 T 工具注册", "### 4.3 C 上下文管理",
        "### 4.4 S 状态存储", "### 4.5 L 生命周期钩子", "### 4.6 V 评估接口",
        "## 5. 模型组合与任务分派",
    ]
    idx = [text.find(b) for b in bounds]
    is_true(all(i >= 0 for i in idx), f"模板 §4 各层标题应可定位，实际命中位置 {idx}")
    return {layer: text[idx[i]:idx[i + 1]] for i, layer in enumerate("ETCSLV")}


def _template_body() -> str:
    """取出 assets/design-doc.md 里被 ```markdown 包着的那份模板正文。"""
    text = DESIGN_TEMPLATE.read_text(encoding="utf-8")
    m = re.search(r"```markdown\n(.*?)\n```\n\n---", text, re.DOTALL)
    is_true(m is not None, "模板里应能定位到 ```markdown 代码块")
    return m.group(1)


def test_template_filled_hits_43_and_exit_zero():
    """P0-3b 验收锚点：按扩充后的模板提示词认真填 → 43/43 且退出码 0。"""
    proc = run(CHECK_DOC, [FROM_TEMPLATE])
    covered, total = _coverage(proc)
    eq(total, 43, "43 问总数")
    eq(covered, 43, "按模板填满的文档应 43/43 覆盖")
    exit_code(proc, 0, "按模板填满的文档应通过门禁")
    contains(proc.stdout, "结论: 结构完整", "按模板填满的文档结论")
    contains(proc.stdout, "未填占位符 <...>: 无", "按模板填满不应有占位符残留")


def test_template_prompts_match_gate_keywords():
    """模板提示词必须与门禁 QUESTION_KEYWORDS 同源：每层每个关键词都要出现在该层提示行里。

    这条用例锁死「照模板填 → 命中 43 问」的前提；以后任一侧改词而另一侧没跟，这里就红。
    """
    gate = _load_gate_module()
    sections = _template_layer_sections()
    missing = []
    for layer, questions in gate.QUESTION_KEYWORDS.items():
        sec = sections[layer].lower()
        for qid, label, keywords in questions:
            if not any(k.lower() in sec for k in keywords):
                missing.append(f"{qid} {label}（关键词: {' / '.join(keywords)}）")
    is_true(not missing, "模板提示行缺少这些问题的对应关键词:\n  - " + "\n  - ".join(missing))


def test_unfilled_template_still_fails():
    """提示词就是关键词，因此必须保证"留着尖括号不填"仍被拦下。

    否则提示词本身会变成免费通行证（不用答题也能凑满 43 问）。
    """
    ws = Workspace()
    try:
        doc = ws.write("unfilled.md", _template_body())
        proc = run(CHECK_DOC, [doc])
        exit_code(proc, 1, "未填写的模板必须返回 1")
        contains(proc.stdout, "未填占位符 <...>: 有", "未填模板应被占位符检查拦下")
    finally:
        ws.cleanup()


def test_partial_template_fills_section13_only_still_fails():
    """P0-3c 加固验证：未填模板只填 §13 结论列（最常见的"敷衍式填空"）必须返回 1。

    P0-3b 之前 41/43 假绿就在这一格上：把 §13 8 行结论填了，其余 63 处尖括号一字不动，
    门禁却判「结论: 结构完整」放行。修法是 placeholders 参与 problems + 五项全过。
    """
    ws = Workspace()
    try:
        tpl = _template_body()
        out = []
        for ln in tpl.splitlines():
            import re as _re
            r = _re.match(r"^\|\s*(\d+)\s*\|([^|]*)\|([^|]*)\|", ln.strip())
            if r and not r.group(3).strip():
                out.append(f"| {r.group(1)} | {r.group(2).strip() or '项'} | 已确认 |")
            else:
                out.append(ln)
        doc = ws.write("partial.md", "\n".join(out))
        proc = run(CHECK_DOC, [doc])
        exit_code(proc, 1, "只填 §13、留着 60+ 处尖括号必须返回 1")
        contains(proc.stdout, "未填占位符 <...>: 有", "占位符必须被检出")
    finally:
        ws.cleanup()


def test_long_placeholder_with_keywords_still_fails():
    """P0-3c 加固验证：把模板里多条提示词合并成一条 >60 字符、含 43 问关键词的长 <…>，
    仍必须被判为未填占位符。

    上一轮阻断-3 实证：长度上限恒为 60 时，所有合并后的长 <…> 一律放行。
    修法：含 43 问关键词的长 <…> 一律仍判占位符。

    本测试用**最小化极简文档**：只有 1 个长 <…>、§13 全部填满、其它问都覆盖。
    长 <…> 必须是**唯一**触发门禁的钩子；这样 M6（让长 <…> 不再判占位符）
    才能被精确测出。
    """
    ws = Workspace()
    try:
        # 极简文档：六层各 1-2 句陈述覆盖全部 43 问，§13 全部填满，
        # 只在 §4.1 留一个 >60 字符、含 43 问关键词的长 <…>。
        # 没有这个长 <…>，门禁全过。
        merged = ("<E 层九问合并作答：终止条件归属、防跑飞（轮次上限 / token 预算 / 每节点超时）、"
                  "静态模式 还是 动态脚本、失败回喂 与分类恢复、打转检测（参数指纹）、循环内档位分派、"
                  "策略选择器由谁实现、墙钟预算与并行度、流式与可中断——请逐条作答>")
        sec_E = f"""## 4.1 E 执行循环
{merged}"""
        sec_T = """## 4.2 T 工具注册
工具接入按 MCP 标准化接口；按需筛选子集，超过 80 件时按 task type 收窄；执行环境统一沙箱（Docker 隔离）；凭证不进执行环境，凭证走外部代理注入；注册仅登记到元数据，披露走 agent profile schema，独立授权按 RBAC + 资源标签；模型组件（决策型 / 快筛）走 in-process 调用；工具披露序列按字典序固定（key 顺序、JSON 序列化、缩进），避免前缀抖动。"""
        sec_C = """## 4.3 C 上下文管理
窗口预算 60k token；预算分配：系统指令 4k、历史 32k、工具结果 12k、参考资料 8k；超过 50% 后开始压缩与摘要，按语义而非句法切片；噪音（工具 raw output、检索原文）下沉到子任务的 scratch file；每轮重新组装上下文（fresh prompt build）；外部内容消毒：截断到 4k + 标记为「待分析数据」不可被解释为指令；决策型模型 state 复用上下文组装结果；前缀稳定区 = 系统指令 + 工具披露序列 + 角色名，可变尾部 = 历史 + 当前轮；重写失效预算 = 单轮 ≤ 2 次全量重写，昂贵中间结果（语法树、检索 doc id 集合）复用。"""
        sec_S = """## 4.4 S 状态存储
存储结构用 SQLite（KV 索引）；写操作全部经治理层（Agent 只能 append structured log，状态变更走 StateService）；失败后从 sqlite checkpoint 重新加载，加载有可审计 trail；并发写用 WAL + 单写者（wals）；外部副作用幂等：每个外部写带 idempotency_key，恢复策略=先 query 实际状态再 decide；记忆治理：每条 memo 标 source 字段、ttl 字段、unverified 标记，被引用 ≥3 次才升格事实；证据版本绑定：评估结论附 evidence_version，版本不匹配时该结论自动失效。"""
        sec_L = """## 4.5 L 生命周期钩子
拦截点：pre-invoke 鉴权、post-invoke 审计、policy 强制、安全监控；拦截不可绕过，写在 SDK 内部，agent 不能 disable；鉴权走 OAuth2 + OIDC，token 校验独立服务；人在回路分四档：自动执行 / 事后告知 / 事前确认 / 直接阻断，审批量大时降级到 LLM triage 助手；高危拦截纵深：pre 过滤器 + 独立后置分类器，路径不同；快筛阈值 0.92、放行率 1/1000，注入鲁棒性测试每月跑一次。"""
        sec_V = """## 4.6 V 评估接口
独立验证：随机抽 30% 子集走 ground truth 对比；客观手段：自动化 diff + 黄金集；评估者分离：评估 prompt 完全独立，看不到执行者 chain-of-thought，只看最终输出与执行 log；标准显式：每条评估项附 pass criterion，迭代预算 5 轮；工具回执（HTTP 200）≠ 业务事实，核对权威系统（DB / 业务对象）实际状态；评测环境可比：同一 infra / 同一预算 / 同一 prompt template；用「绕过任务」探测器（已知 harness fail mode）测鲁棒性；验证强度阶梯：本设计走 L2（自动化 + 黄金集），不上升到 L3（人工 spot check）。"""
        body = (
            "# 测试文档\n\n"
            + sec_E + "\n\n" + sec_T + "\n\n" + sec_C + "\n\n"
            + sec_S + "\n\n" + sec_L + "\n\n" + sec_V + "\n\n"
            + "## 设计台账\n\n| 版本 | v1 |\n|------|----|\n\n"
            + "## 13. 生产级必答项\n\n"
            + "| # | 必答项 | 结论 |\n|---|--------|------|\n"
            + "| 1 | 执行环境 | 沙箱 |\n| 2 | 错误回喂 | 是 |\n| 3 | 打转检测 | 是 |\n"
            + "| 4 | 记忆治理 | 是 |\n| 5 | 幂等 | 是 |\n| 6 | 版本绑定 | 是 |\n"
            + "| 7 | 评估者分离 | 是 |\n| 8 | 模型组合 | 是 |\n| 9 | 前缀稳定 | 是 |\n"
        )
        doc = ws.write("long_placeholder_only.md", body)
        proc = run(CHECK_DOC, [doc])
        # 长 <…> 必须出现在占位符列表里（这一条是 43 问关键词长 <…> 的核心防护）
        contains(proc.stdout, "未填占位符 <...>: 有", "合并后的长 <…> 必须出现在占位符列表里")
        exit_code(proc, 1, "只有 1 个长 <…> 未填，门禁必须返回 1")
    finally:
        ws.cleanup()


def test_keyword_word_boundary_blocks_english_false_match():
    """P0-3c 加固验证：纯 ASCII 关键词（wal / state / jwt）用词边界匹配，
    避免 paywall / statement / Cornwall 等英文普通词误命中。

    上一轮阻断-2 实证：'wal' 在 'The paywall blocks access.' 中命中。
    修法：纯 ASCII 关键词走 \\b 词边界。
    """
    ws = Workspace()
    try:
        # 构造一份 S3（wal 关键词）走空话、其它层都「按模板认真填」的长文档：
        # 若 wal 仍走子串匹配，本测试文档会被错判为 S3 覆盖 → §4.4 长度够 200 字符
        # → 通过；走词边界匹配时，wal 不在 paywall 中命中 → §4.4 整层被 MIN_SECTION_CHARS 卡住
        # 也不一定。简化：本测试直接断言 S3 在「wal 出现在 paywall 中」时不计覆盖。
        import importlib.util as _ilu
        from _harness import run as _run
        # 取 design_full 的 §4.4 段并把 'wal' 改写成 paywall / statement
        text = ws.read if False else None
        tpl = _template_body()
        # 真实校验逻辑直接调用 verify：
        spec = _ilu.spec_from_file_location("cdd", CHECK_DOC)
        mod = _ilu.module_from_spec(spec); spec.loader.exec_module(mod)
        body = mod._strip_fenced("Walrus observed. Paywall enforced. State-of-art declared.")
        rx = mod._KEYWORD_RX.get("wal")
        is_true(rx is not None, "纯 ASCII 关键词应编译为带 \\b 的正则")
        is_true(not rx.search("Paywall"),
                "纯 ASCII 关键词 wal 不应在 paywall 中命中（词边界保护）")
        is_true(rx.search("wal stored"),
                "纯 ASCII 关键词 wal 仍应在独立单词中命中")
    finally:
        ws.cleanup()


def test_missing_file_is_error():
    ws = Workspace()
    try:
        proc = run(CHECK_DOC, [ws.path / "nope.md"])
        exit_code(proc, 1, "不存在的文档应报错退出 1")
        contains(proc.stderr + proc.stdout, "文件不存在", "文件不存在提示")
    finally:
        ws.cleanup()


# ---------------------------------------------------------------------------
# P3-1：MUST_ANSWER 限域到 §4.1-§4.6（仅"模型组合"不限域）
# ---------------------------------------------------------------------------

# 极简"按模板认真填"基线文档：六层各一句陈述、§13 结论列已填、所有 MUST_ANSWER
# 关键词都放在**正确**层号段。这是 P3-1 测试的对照锚点。
_P31_BASELINE = """# 测试文档

## 1. 需求规格

略。

## 2. 架构范式 P

略。

## 3. 技术栈选型

略。

## 4. 六层设计

### 4.1 E 执行循环
失败回喂：模型自评是循环论证。打转检测：连续 3 次同参数指纹熔断。

### 4.2 T 工具注册
工具接入：ToolSpec 声明。凭证：外部代理注入；执行环境：容器内沙箱。

### 4.3 C 上下文管理
每轮重新组装：fresh build。前缀稳定：序列化确定性，key 顺序固定。

### 4.4 S 状态存储
记忆治理：可信度 + 归属 + TTL。幂等：idempotency_key + 状态查询。版本绑定：content_version 绑定证据。

### 4.5 L 生命周期钩子
拦截点：pre/post + policy + 安全监控。人在回路分四档。

### 4.6 V 评估接口
评估者分离：独立上下文 + 独立评分卡。迭代预算 3 轮。

## 5. 模型组合与任务分派
模型组合：决策型 + 快速低价 + 强力。

## 6. 多 Agent 编排

不适用。

## 7. 模块 / 目录结构

略。

## 8. 关键接口签名

略。

## 9. 核心数据结构

略。

## 10. 配置文件格式

略。

## 11. 层间交叉检查

略。

## 12. 六层决策表

略。

## 13. 生产级必答项

| # | 必答项 | 结论 |
|---|--------|------|
| 1 | 执行环境 | 沙箱 |
| 2 | 错误回喂 | 是 |
| 3 | 打转检测 | 是 |
| 4 | 记忆治理 | 是 |
| 5 | 幂等 | 是 |
| 6 | 版本绑定 | 是 |
| 7 | 评估者分离 | 是 |
| 8 | 模型组合 | 是 |
| 9 | 前缀稳定 | 是 |

## 14. 参考架构图

略。

## 15. 遗留问题与未知区

略。
"""


def test_p31_must_answer_baseline_9_of_9():
    """P3-1 锚点：基线文档中所有 MUST_ANSWER 关键词均落在正确层号段 → 9/9 通过。"""
    ws = Workspace()
    try:
        doc = ws.write("baseline.md", _P31_BASELINE)
        proc = run(CHECK_DOC, [doc])
        contains(proc.stdout, "生产级必答项: 9/9", "基线文档应 9/9 通过（P3-1 限域生效）")
        # 不退出码：基线还有其它门禁（§13 表 8 行而非 9 行——见 §13 行数检查）。
        # 本测试只断言 MUST_ANSWER 这一行的覆盖数字，不强求整体退出码。
    finally:
        ws.cleanup()


def test_p31_must_answer_wrong_layer_not_covered():
    """P3-1 核心验收：限域关键词放在**错误**层号段不算覆盖。

    例如「错误回喂」本属 §4.1 E，但把它从 §4.1 E 段删掉、改放到 §4.3 C 段；
    「执行环境」本属 §4.2 T，但放到 §4.5 L 段。这些都不应算覆盖。
    """
    ws = Workspace()
    try:
        # 在基线基础上，把「错误回喂」从 §4.1 移到 §4.3（错误的层号段）
        # 「执行环境」从 §4.2 移到 §4.5 L 段
        body = _P31_BASELINE
        body = body.replace(
            "### 4.1 E 执行循环\n失败回喂：模型自评是循环论证。打转检测：连续 3 次同参数指纹熔断。",
            "### 4.1 E 执行循环\n打转检测：连续 3 次同参数指纹熔断。",
        )
        body = body.replace(
            "### 4.3 C 上下文管理\n每轮重新组装：fresh build。前缀稳定：序列化确定性，key 顺序固定。",
            "### 4.3 C 上下文管理\n每轮重新组装：fresh build。错误回喂：模型自评是循环论证。前缀稳定：序列化确定性，key 顺序固定。",
        )
        body = body.replace(
            "### 4.2 T 工具注册\n工具接入：ToolSpec 声明。凭证：外部代理注入；执行环境：容器内沙箱。",
            "### 4.2 T 工具注册\n工具接入：ToolSpec 声明。凭证：外部代理注入。",
        )
        body = body.replace(
            "### 4.5 L 生命周期钩子\n拦截点：pre/post + policy + 安全监控。人在回路分四档。",
            "### 4.5 L 生命周期钩子\n拦截点：pre/post + policy + 安全监控。人在回路分四档。执行环境：容器内沙箱。",
        )
        doc = ws.write("wrong_layer.md", body)
        proc = run(CHECK_DOC, [doc])
        contains(proc.stdout, "生产级必答项: 7/9",
                 "「错误回喂」+「执行环境」放错层号段 → 从 9/9 收紧到 7/9")
        contains(proc.stdout, "未出现:",
                 "缺项应被点名（输出「未出现:」行）")
        # 用 contains 验证「错误回喂」「执行环境」出现在未出现行
        for missing in ("错误回喂", "执行环境"):
            contains(proc.stdout, missing, f"未出现项应列出 {missing!r}")
        exit_code(proc, 1, "MUST_ANSWER 跨错层应卡门禁")
    finally:
        ws.cleanup()


def test_p31_must_answer_cross_layer_unbounded():
    """P3-1 加固：「模型组合」跨 E/T/C 三档，由 §5 模型组合与任务分派承载，
    MUST_ANSWER_LAYERS 中标为 None → 全文档命中即覆盖（不限域）。"""
    ws = Workspace()
    try:
        # 基线中「模型组合」在 §5 标题与正文出现 → 不限域，应命中
        doc = ws.write("cross_layer.md", _P31_BASELINE)
        proc = run(CHECK_DOC, [doc])
        # 模型组合必须出现在「未出现」列表之外（基线应 9/9 或仅缺其它项）
        # 基线是 9/9，此测试单独跑 cross_layer.html 也能拿到「模型组合」覆盖
        # ——直接在模块层验证不限域逻辑更精确。
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location("cdd31x", CHECK_DOC)
        mod = _ilu.module_from_spec(spec); spec.loader.exec_module(mod)
        # 模块层断言：「模型组合」必须在 MUST_ANSWER_LAYERS 中标记为 None
        is_true(
            mod.MUST_ANSWER_LAYERS.get("模型组合") is None,
            "「模型组合」必须标为不限域（None），跨 E/T/C 归 §5 承载",
        )
        # 限域关键词必须有层号（非 None）
        for label in ("执行环境", "错误回喂", "打转检测", "记忆治理",
                      "幂等", "版本绑定", "评估者分离", "前缀稳定"):
            is_true(
                mod.MUST_ANSWER_LAYERS.get(label) in mod.LAYER_SECTION,
                f"限域关键词 {label!r} 必须有有效层号",
            )
        # 函数行为验证：在「模型组合」不出现在文档中的极端情况下不限域 -> 该项缺失；
        # 在「模型组合」出现在文档中则不限域命中 -> 该项覆盖。
        empty_body = mod._strip_fenced("# 测试\n无任何关键词。\n")
        empty_sections = mod.split_layer_sections(empty_body)
        missing, _ = mod.find_missing_must_answer("", empty_body, empty_sections)
        contains(" ".join(missing), "模型组合",
                 "无任何关键词的文档里「模型组合」应被记为缺失")
        # 给一具含「模型组合」的极简 body
        hit_body = mod._strip_fenced("# 测试\n## 5. 模型组合与任务分派\n模型组合按档位分。\n")
        hit_sections = mod.split_layer_sections(hit_body)
        missing2, _ = mod.find_missing_must_answer("", hit_body, hit_sections)
        not_in = "模型组合" not in missing2
        is_true(not_in, "「模型组合」出现在 §5 任意位置不限域命中，应不在缺失列表")
    finally:
        ws.cleanup()


def test_p31_must_answer_missing_layer_section_falls_back_to_full_doc():
    """P3-1 加固：限域段不存在（如 §4.4 S 段被吞）→ 退回全文档匹配并报结构性问题。

    例如 S 层段落没了但「记忆治理」/「幂等」/「版本绑定」仍出现在全文其它位置
    （§5/§13），按"退回全文档"原则视为覆盖。同时结构性列表里应明示段位缺失。
    """
    ws = Workspace()
    try:
        # 在模块层直接验证：人为构造一份缺 §4.4 S 段的 body，
        # 把 S 相关关键词塞到 §5 模型组合的正文里
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location("cdd31s", CHECK_DOC)
        mod = _ilu.module_from_spec(spec); spec.loader.exec_module(mod)
        body_no_S = mod._strip_fenced("""# 测试

## 4.1 E 执行循环
错误回喂：模型自评是循环论证。

## 4.2 T 工具注册
工具接入：ToolSpec。执行环境：容器内沙箱。

## 4.3 C 上下文管理
每轮重新组装。前缀稳定：序列化确定。

## 4.5 L 生命周期钩子
拦截点：pre/post。

## 4.6 V 评估接口
评估者分离：独立上下文 + 独立评分卡。

## 5. 模型组合与任务分派
记忆治理：可信度 + TTL。幂等：idempotency_key。版本绑定：content_version。

## 13. 生产级必答项

| # | 必答项 | 结论 |
|---|--------|------|
| 1 | 执行环境 | 是 |
| 2 | 错误回喂 | 是 |
| 3 | 打转检测 | 是 |
| 4 | 记忆治理 | 是 |
| 5 | 幂等 | 是 |
| 6 | 版本绑定 | 是 |
| 7 | 评估者分离 | 是 |
| 8 | 模型组合 | 是 |
| 9 | 前缀稳定 | 是 |
""")
        sections = mod.split_layer_sections(body_no_S)
        # §4.4 S 段应不在（确认测试前提成立）
        is_true(4 not in sections, "测试前提：§4.4 S 段必须不在")
        missing, structural = mod.find_missing_must_answer("", body_no_S, sections)
        # §4.4 段缺失时，「记忆治理」「幂等」「版本绑定」退回全文档匹配
        # 应在 body 中存在 → 不在 missing 里
        for kw in ("记忆治理", "幂等", "版本绑定"):
            is_true(
                kw not in missing,
                f"限域段缺失时 {kw!r} 应退回全文档匹配并视为覆盖",
            )
        # 但应报结构性问题
        structural_str = " ".join(structural)
        contains(structural_str, "§4.4", "限域段缺失应报结构性问题（含 §4.4）")
        contains(structural_str, "段落缺失",
                 "限域段缺失应明示「段落缺失」字样")
        # 反向断言：有 §4.4 段但段内无 S 关键词，应记为缺失
        body_with_empty_S = mod._strip_fenced("""# 测试

## 4.4 S 状态存储
略。

## 13. 生产级必答项
略。
""")
        sections_with_S = mod.split_layer_sections(body_with_empty_S)
        is_true(4 in sections_with_S, "测试前提：§4.4 S 段必须存在")
        missing2, _ = mod.find_missing_must_answer("", body_with_empty_S, sections_with_S)
        # 「记忆治理」段内无 → 应记为缺失（不退回全文档）
        is_true("记忆治理" in missing2,
                "有限域段但段内无关键词时，必须记为缺失（不退回全文档）")
    finally:
        ws.cleanup()
