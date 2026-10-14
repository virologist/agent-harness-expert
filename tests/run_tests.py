#!/usr/bin/env python3
"""专家包脚本冒烟测试总入口（纯标准库）。

用法:
    python3 tests/run_tests.py            跑全部
    python3 tests/run_tests.py check      只跑模块名含 "check" 的用例

退出码：全通过 0；任一失败 1。
每个用例真实执行脚本、真实断言退出码与输出；工作区在 tmp，跑完清理。
"""
from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
MODULES = [
    "test_check_design_doc",
    "test_lint_knowledge",
    "test_architect_scripts",
    "test_wiki_scripts",
]


def _load(module_name: str):
    """按文件路径加载测试模块（tests/ 不是包，且不依赖调用方 cwd）。"""
    spec = importlib.util.spec_from_file_location(module_name, TESTS_DIR / f"{module_name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载测试模块: {module_name}")
    mod = importlib.util.module_from_spec(spec)
    # 让测试模块能 import 同目录的 _harness
    if str(TESTS_DIR) not in sys.path:
        sys.path.insert(0, str(TESTS_DIR))
    spec.loader.exec_module(mod)
    return mod


def collect(module_name: str) -> list:
    mod = _load(module_name)
    items = [(name, getattr(mod, name)) for name in sorted(dir(mod)) if name.startswith("test_")]
    return [(f"{module_name}::{name}", fn) for name, fn in items if callable(fn)]


def main() -> int:
    filt = sys.argv[1] if len(sys.argv) > 1 else ""
    cases = []
    for m in MODULES:
        if filt and filt not in m:
            continue
        cases.extend(collect(m))

    if not cases:
        print(f"没有匹配到任何用例（filter={filt!r}）")
        return 1

    passed, failed = 0, []
    print(f"运行 {len(cases)} 个用例（模块: {', '.join(m for m in MODULES if not filt or filt in m)}）\n")
    for full_name, fn in cases:
        try:
            fn()
        except AssertionError as e:
            failed.append((full_name, str(e)))
            print(f"[FAIL] {full_name}\n       {e}")
        except Exception:  # 脚本崩溃 / 环境问题同样是失败，不静默
            failed.append((full_name, traceback.format_exc()))
            print(f"[ERROR] {full_name}\n{traceback.format_exc()}")
        else:
            passed += 1
            print(f"[PASS] {full_name}")

    print(f"\n结果: 通过 {passed} / {len(cases)}，失败 {len(failed)}")
    if failed:
        print("\n失败清单:")
        for name, msg in failed:
            print(f"  - {name}: {msg.splitlines()[0] if msg else ''}")
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
