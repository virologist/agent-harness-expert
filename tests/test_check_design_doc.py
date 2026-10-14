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
    """43 问检查是叠加项：原有检查（台账 / 占位符 / §13）仍在工作。"""
    proc = run(CHECK_DOC, [HEADINGS_ONLY])
    contains(proc.stdout, "设计台账行: 有", "台账检查仍执行")
    contains(proc.stdout, "§13 必答项结论空缺: 无", "§13 检查仍执行")
    contains(proc.stdout, "生产级必答项: 9/9", "必答项检查仍执行")


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


def test_missing_file_is_error():
    ws = Workspace()
    try:
        proc = run(CHECK_DOC, [ws.path / "nope.md"])
        exit_code(proc, 1, "不存在的文档应报错退出 1")
        contains(proc.stderr + proc.stdout, "文件不存在", "文件不存在提示")
    finally:
        ws.cleanup()
