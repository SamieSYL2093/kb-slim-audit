#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_slim 回归自检：拿 tests/fixtures/ 的已知问题样本扫一遍，断言该报的全报、不该报的不报。

为什么需要它（SKILL.md §十四）：脚本报"全绿"不算数——改完脚本后，
已知问题必须还能被全部抓出，否则就是"真空绿"。

用法：
    python scripts/kb_slim_selftest.py     # 退出码 0 = 全部通过；1 = 有失败项

新增案例：往 tests/fixtures/ 放样本文件 + 在 expected.json 里加一条断言，不动本脚本。
注意：fixtures/ 里的冗余是故意埋的（见 tests/README.md），别去"修复"它们。
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

# Windows GBK 控制台会炸 emoji — 强制 UTF-8
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = Path(__file__).resolve().parent.parent
FIXTURES = BASE / "tests" / "fixtures"


def load_scanner():
    """按路径加载 kb_slim_scan.py（免安装、免包结构）。"""
    spec = importlib.util.spec_from_file_location(
        "kb_slim_scan", BASE / "scripts" / "kb_slim_scan.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main() -> int:
    expect = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))
    scan = load_scanner()
    _mds, findings, kws, _center = scan.scan(FIXTURES, None, 300, 10)
    got = [(f[3], f[4]) for f in findings]

    fails = []
    need_kws = expect.get("min_center_keywords", 0)
    if len(kws) < need_kws:
        fails.append(f"中心文档关键词 {len(kws)} < {need_kws}：S3 复述检测可能已静默失效")

    # §十四 契约断言：每条 finding 必须带规则 ID（S 开头 + 数字）与置信度（高/中）
    bad = [f for f in findings
           if not (len(f) == 7 and re.fullmatch(r"S\d+", str(f[0])) and f[2] in ("高", "中"))]
    if bad:
        fails.append(f"{len(bad)} 条 finding 缺规则 ID 或置信度（违反 §十四 findings 契约）")

    def hit(rule):
        return any(rule["category"] == c and rule["location_contains"] in loc
                   for c, loc in got)

    for rule in expect.get("expect", []):
        ok = hit(rule)
        print(("  ✅ " if ok else "  ❌ ")
              + f"应报：[{rule['category']}] {rule['location_contains']}")
        if not ok:
            fails.append(f"应报未报：[{rule['category']}] {rule['location_contains']}")
    for rule in expect.get("reject", []):
        bad = hit(rule)
        print(("  ❌ " if bad else "  ✅ ")
              + f"不应报：[{rule['category']}] {rule['location_contains']}")
        if bad:
            fails.append(f"误报：[{rule['category']}] {rule['location_contains']}")

    print()
    if fails:
        print(f"回归自检失败 {len(fails)} 项：")
        for f in fails:
            print(f"  - {f}")
        return 1
    print(f"回归自检通过：{len(expect.get('expect', []))} 条应报全中、"
          f"{len(expect.get('reject', []))} 条不误报、中心文档关键词 {len(kws)} 个。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
