#!/usr/bin/env python3
"""A-Evolve benchmark（P2-6 落地）：跑 check_design_doc + 43 问覆盖评分。

设计文档样本在 evals/samples/，每个 .md 配一个 .json 元数据：

    {
      "name": "<样本名>",
      "kind": "positive" | "negative" | "boundary",
      "expectation": {
        "exit_code": 0 | 1,
        "min_43q_coverage": <0-43>,   // positive 样本必须达到的最低覆盖
        "max_unanswered": <int>,      // 允许未填结论的最大行数（negative 故意超出）
        "max_placeholders": <int>
      },
      "notes": "<为什么是这档样本>"
    }

每版发布前跑一次，输出：
  - 终端表格（每个样本的实际 vs 期望）
  - 落盘 evals/results/<version>.json 供跨版本对比

退出码：
  0 = 所有样本达到期望
  1 = 任意样本未达期望（门禁失败）
  2 = 跑分过程中脚本/样本异常
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SAMPLES_DIR = ROOT / "samples"
RESULTS_DIR = ROOT / "results"
CHECK_DOC = Path(__file__).resolve().parents[1] / "skills/agent-harness-architect/scripts/check_design_doc.py"

# 从 check_design_doc.py 解析 total_questions
def _total_questions() -> int:
    src = CHECK_DOC.read_text(encoding="utf-8")
    m = re.search(r"def total_questions\(\).*?return\s+(\d+)", src, re.DOTALL)
    if not m:
        return 43
    return int(m.group(1))


def _run_check(doc: Path, template: str = "harness") -> dict:
    """v1.7.2 起按 sample 指定模板（默认 harness，向后兼容）。"""
    proc = subprocess.run(
        [sys.executable, str(CHECK_DOC), str(doc), "--template", template],
        capture_output=True, text=True, timeout=60,
    )
    out = proc.stdout + proc.stderr
    # 解析覆盖行（v1.7.2 problem-solution 模板下输出「未启用」字样，无 X/43 数字）
    coverage_match = re.search(r"六层必答问题覆盖:\s*(\d+)/(\d+)", out)
    if not coverage_match:
        coverage_match = re.search(r"(\d+)/43", out)
    coverage = int(coverage_match.group(1)) if coverage_match else 0
    total = int(coverage_match.group(2)) if coverage_match else 43
    # 解析未填占位符
    ph_match = re.search(r"未填占位符 <\.\.\.>:\s*(.*)", out)
    placeholders = 0
    if ph_match and "无" not in ph_match.group(1):
        # "有，需补写 N 处 → ..."
        n_match = re.search(r"(\d+)\s*处", ph_match.group(1))
        if n_match:
            placeholders = int(n_match.group(1))
    # 解析 §13 未填
    u_match = re.search(r"§13 必答项结论空缺:\s*(\d+)\s*处", out)
    unanswered = int(u_match.group(1)) if u_match else 0
    return {
        "exit_code": proc.returncode,
        "coverage": coverage,
        "total": total,
        "placeholders": placeholders,
        "unanswered": unanswered,
    }


def run(samples_dir: Path, version: str) -> int:
    if not samples_dir.is_dir():
        print(f"samples 目录不存在: {samples_dir}", file=sys.stderr)
        return 2
    results = []
    fail = False
    print(f"{'样本':<32} {'kind':<10} {'rc':<4} {'43问':<6} {'未填':<6} {'占位':<6} {'判定':<6}")
    print("-" * 80)
    for meta_path in sorted(samples_dir.glob("*.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        doc = meta_path.with_suffix(".md")
        if not doc.is_file():
            print(f"[缺] {meta['name']}: 找不到对应 .md", file=sys.stderr)
            fail = True
            continue
        # v1.7.2 起按 sample.template 选模板（默认 harness，向后兼容）
        template = meta.get("template", "harness")
        actual = _run_check(doc, template=template)
        exp = meta["expectation"]
        ok = (
            actual["exit_code"] == exp.get("exit_code", 0)
            and actual["coverage"] >= exp.get("min_43q_coverage", 0)
            and actual["unanswered"] <= exp.get("max_unanswered", 999)
            and actual["placeholders"] <= exp.get("max_placeholders", 999)
        )
        verdict = "PASS" if ok else "FAIL"
        if not ok:
            fail = True
        print(
            f"{meta['name']:<32} {meta['kind']:<10} "
            f"{actual['exit_code']:<4} {actual['coverage']}/{actual['total']:<3} "
            f"{actual['unanswered']:<6} {actual['placeholders']:<6} {verdict:<6}"
        )
        results.append({"name": meta["name"], "kind": meta["kind"], "actual": actual, "expectation": exp, "verdict": verdict})
    # 落盘（P2-6 收尾：safe_mkdir 兼容 WorkBuddy 沙箱会拦 mkdir(exist_ok=True) 误报 EEXIST）
    try:
        RESULTS_DIR.mkdir(parents=True)
    except (FileExistsError, PermissionError) as e:
        # PermissionError(EEXIST) 是沙箱已知 bug（与 wiki-creator _root.safe_mkdir 同源）
        if not RESULTS_DIR.is_dir():
            raise e
    out_path = RESULTS_DIR / f"{version}.json"
    summary = {
        "version": version,
        "total_questions": _total_questions(),
        "samples": results,
        "all_pass": not fail,
    }
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已落盘: {out_path}")
    return 0 if not fail else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="设计文档门禁 benchmark")
    ap.add_argument("--version", required=True, help="版本标签（写入 results/<version>.json）")
    ap.add_argument("--samples", default=str(SAMPLES_DIR), help="样本目录")
    args = ap.parse_args()
    return run(Path(args.samples), args.version)


if __name__ == "__main__":
    raise SystemExit(main())
