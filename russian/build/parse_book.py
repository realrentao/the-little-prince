# -*- coding: utf-8 -*-
"""
把 Маленький_принц.md 解析成结构化章节数据。
输出: build/_parsed.json
"""
import json
import os
import re
import sys

SRC = r"C:\Users\迪丽希斯\OneDrive\Desktop\Маленький_принц.md"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_parsed.json")

# 出版社版权/книжные метаданные 样板 —— 非正文，过滤掉
SKIP_PATTERNS = [
    r"ISBN",
    r"ББК",
    r"УДК",
    r"^©",
    r"СЗКЭО",
    r"Творческое объединение",
    r"Malmero",
    r"^Санкт-Петербург",
    r"переплётной компании",
    r"переплетной компании",
    r"пронумерованных экземпляров",
]
SKIP_RE = [re.compile(p) for p in SKIP_PATTERNS]


def is_boilerplate(text: str) -> bool:
    for r in SKIP_RE:
        if r.search(text):
            return True
    return False


def norm(text: str) -> str:
    """规范化标点/空白：修掉 PDF 抽取残留的连字符换行、多空格。"""
    t = text.replace("\u00a0", " ")
    # PDF 抽词换行残留: "оде- ваться" -> "одеваться"
    t = re.sub(r"([а-яё])-\s+([а-яё])", r"\1\2", t)
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def main():
    raw = open(SRC, encoding="utf-8").read().replace("\ufeff", "")
    lines = raw.split("\n")

    sections = []  # {level, title, paras[]}
    cur = None
    for line in lines:
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^(#+)\s*(.+)$", s)
        if m:
            cur = {"level": len(m.group(1)), "title": m.group(2).strip(), "paras": []}
            sections.append(cur)
            continue
        if cur is None:
            continue
        cur["paras"].append(s)

    # 归一 + 过滤
    chapters = []
    for sec in sections:
        keep = []
        for p in sec["paras"]:
            if is_boilerplate(p):
                continue
            p = norm(p)
            if len(p) < 2:
                continue
            keep.append(p)
        chapters.append({"title": sec["title"], "paras": keep})

    # 报告
    total = 0
    print("=== sections ===")
    for i, c in enumerate(chapters):
        n = len(c["paras"])
        total += n
        print(f"[{i:02d}] {c['title']!r}  paras={n}")
    print("total paras kept:", total)

    json.dump(chapters, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("written:", OUT)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
