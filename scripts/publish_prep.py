#!/usr/bin/env python3
"""发布准备：生成项目内的待发布副本 publish/，并统一一次性脱敏。

设计意图（用户 2026-08-28）：
    制作/升级 skill 的过程不必一直惦记脱敏——那会拖慢内容打磨。
    脱敏是**发布时**的一次性动作：从本体生成副本，统一替换，复检过关再发。

用法：
    python scripts/publish_prep.py            # 生成/刷新 publish/（复制 + 脱敏 + 复检）
    python scripts/publish_prep.py --check    # 只扫描本体，不生成
    python scripts/publish_prep.py --list     # 打印白名单与排除项

原则（本 skill 判定式 15 单源化）：
    publish/ 是**生成物**，从本体生成，不手工编辑。
    要改内容就改本体再跑一次；直接改 publish/ 会在下次生成时被覆盖。
"""

import argparse
import json
import os
import re
import shutil
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── 白名单：只有这些进发布面 ──────────────────────────────
WHITELIST_FILES = ["SKILL.md", "README.md", "LICENSE", "CHANGELOG.md"]
WHITELIST_DIRS = ["scripts", "references", "tests"]
# 目录进了白名单，但其中仅供本仓内部使用的工具不发布（对使用者无意义）
EXCLUDE_FILES = {
    "api_push.py",  # 把发布面推到 GitHub 的上传工具，只服务于本仓发布流程
}

OUT_DIR = "publish"
CONFIG_NAME = ".sensitive-patterns.json"

# ── 通用脱敏规则（任何组织都适用，不是私有事实）────────────
# 注意：规则表本身不要字面写出敏感词，否则规则表自己先中枪（见 SKILL.md 案例库）
GENERIC_REPLACE = [
    (re.compile(r"(?<![a-zA-Z/])[A-Za-z]:[\\/](?!//)"), "your-dir/"),
    (re.compile(r"\b[PGXR]-\d{2,4}\b"), "X-NN"),
    (re.compile(r"\bG\d{3}\b"), "G-NNN"),
    # 规范编号段（1-XX/2-XX/3-XX 系）：08-29 根治——1.5.4 已发布面曾漏过下划线连写的
    # 编号文件名（复检全绿），姊妹技能仓先行修复后回灌本机制源。lookahead 兼容下划线形态；
    # 8/9 开头的日期类编号（如 8-01）刻意不收，防误伤。替换目标不含数字，不会被二次匹配。
    (re.compile(r"\b[123]-\d{2}(?=\b|_)"), "X-NN"),
]
# 注意：替换目标不能写成"字母-数字"样式，否则会被自己的规则二次匹配（本文件注释里的举例就被换过一次）


def base_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config(base: str):
    """读 .sensitive-patterns.json。

    格式：{ "_replace": {原串: 替换串}, "显示名": ["词", ...] }
    _replace 同时用于「检查」和「替换」——一张表两用，不会漏。
    """
    path = os.path.join(base, CONFIG_NAME)
    if not os.path.exists(path):
        return {}, {}
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except (ValueError, OSError) as exc:
        print(f"[警告] 配置文件读取失败，已跳过：{exc}")
        return {}, {}
    replace = {k: v for k, v in raw.get("_replace", {}).items() if k}
    names = {k: v for k, v in raw.items()
             if not k.startswith("_") and isinstance(v, list)}
    return replace, names


def check_patterns(replace: dict, names: dict) -> dict:
    """把 _replace 与分组词表合成检查用正则表。"""
    rules = {
        "本机绝对路径": GENERIC_REPLACE[0][0],
        "内部编号": re.compile(r"\b[PGXR]-\d{2,4}\b|\bG\d{3}\b|P\d{2}(?=[-\u4e00-\u9fa5])|\b[123]-\d{2}(?=\b|_)"),
    }
    for word in replace:
        rules.setdefault("私有词", [])
    if replace:
        rules["私有词"] = re.compile(
            "|".join(re.escape(w) for w in sorted(replace, key=len, reverse=True)))
    for name, words in names.items():
        rules[name] = re.compile("|".join(re.escape(w) for w in words))
    return {k: v for k, v in rules.items() if not isinstance(v, list)}


def collect(base: str):
    keep, drop = [], []
    for name in sorted(os.listdir(base)):
        if name.startswith(".") or name in (OUT_DIR, "dist"):
            continue
        path = os.path.join(base, name)
        if os.path.isdir(path):
            (keep if name in WHITELIST_DIRS else drop).append(name + "/")
        elif name in WHITELIST_FILES:
            keep.append(name)
        elif name.endswith((".pyc", ".bak")):
            continue
        else:
            drop.append(name)
    return keep, drop


def sanitize_text(text: str, replace: dict) -> tuple:
    """应用脱敏：先私有词表，再通用规则。返回 (新文本, 命中计数)。"""
    hits = {}
    for word, sub in sorted(replace.items(), key=lambda kv: -len(kv[0])):
        n = text.count(word)
        if n:
            text = text.replace(word, sub)
            hits[word] = n
    for pat, sub in GENERIC_REPLACE:
        text, n = pat.subn(sub, text)
        if n:
            hits[sub] = hits.get(sub, 0) + n
    return text, hits


def walk_files(base: str, rels):
    """展开目录，返回 [(绝对路径, 相对路径)]。"""
    out = []
    for rel in rels:
        path = os.path.join(base, rel)
        if os.path.isdir(path):
            for root, _d, names in os.walk(path):
                if "__pycache__" in root:
                    continue
                for n in names:
                    if n.endswith((".pyc", ".bak")) or n in EXCLUDE_FILES:
                        continue
                    full = os.path.join(root, n)
                    out.append((full, os.path.relpath(full, base)))
        else:
            out.append((path, rel))
    return out


TEXT_EXT = (".md", ".py", ".txt", ".json", ".yml", ".yaml", ".cfg", ".toml")


def scan(root: str, rels, rules: dict) -> list:
    hits = []
    for full, rel in walk_files(root, rels):
        if not full.endswith(TEXT_EXT):
            continue
        try:
            text = open(full, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for kind, pat in rules.items():
                if pat.search(line):
                    hits.append((rel, i, kind, line.strip()[:80]))
                    break
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="生成待发布副本 publish/ 并统一脱敏")
    ap.add_argument("--check", action="store_true", help="只扫描本体，不生成")
    ap.add_argument("--list", action="store_true", help="打印白名单与排除项")
    args = ap.parse_args()

    base = base_dir()
    keep, drop = collect(base)
    replace, names = load_config(base)
    rules = check_patterns(replace, names)

    print(f"仓库：{base}")
    print(f"白名单 {len(keep)} 项：{', '.join(keep)}")
    print(f"排除   {len(drop)} 项：{', '.join(drop)}")
    print(f"脱敏映射 {len(replace)} 条 + 通用规则 {len(GENERIC_REPLACE)} 条")

    if args.list:
        return 0

    if args.check:
        hits = scan(base, keep, rules)
        if hits:
            print(f"\n本体含 {len(hits)} 处待脱敏内容（发布时会被替换）：")
            for rel, ln, kind, text in hits[:20]:
                print(f"  {kind}  {rel}:{ln}  {text}")
            if len(hits) > 20:
                print(f"  … 另有 {len(hits) - 20} 处")
        else:
            print("\n本体无需脱敏 ✅")
        return 0

    out = os.path.join(base, OUT_DIR)
    os.makedirs(out, exist_ok=True)
    written = set()

    total = {}
    for full, rel in walk_files(base, keep):
        dst = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dst) or out, exist_ok=True)
        if full.endswith(TEXT_EXT):
            text = open(full, encoding="utf-8").read()
            new, hits = sanitize_text(text, replace)
            open(dst, "w", encoding="utf-8", newline="\n").write(new)
            for k, v in hits.items():
                total[k] = total.get(k, 0) + v
        else:
            shutil.copy2(full, dst)
        written.add(os.path.normpath(dst))

    stale = []
    for root, _d, fs in os.walk(out):
        if "__pycache__" in root:
            continue
        for f in fs:
            p = os.path.normpath(os.path.join(root, f))
            if p not in written:
                stale.append(os.path.relpath(p, out))
    if stale:
        print("\n[注意] publish/ 里有本次未覆盖的旧文件，需手动删除：")
        for s in stale:
            print(f"  {s}")

    if total:
        print("\n已脱敏替换：")
        for k, v in sorted(total.items(), key=lambda kv: -kv[1]):
            print(f"  {v:>3} 处 → {k}")

    left = scan(out, collect(out)[0], rules)
    if left:
        print(f"\n[阻断] publish/ 仍有 {len(left)} 处残留，映射表不完整：")
        for rel, ln, kind, text in left[:20]:
            print(f"  {kind}  {rel}:{ln}  {text}")
        print("\n补齐 .sensitive-patterns.json 的 _replace 后重跑。")
        return 1

    n = sum(len(fs) for _r, _d, fs in os.walk(out))
    print(f"\n脱敏复检：0 残留 ✅")
    print(f"已生成 {out}（{n} 个文件）")
    print(f"发布时只推这个目录：{', '.join(keep)}")
    print("提醒：对外建仓须在 publish/ 副本上全新 git init——不带本仓历史（历史提交含脱敏前信息，连带历史 push 即泄漏）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
