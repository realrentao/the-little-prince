# -*- coding: utf-8 -*-
"""按章节把俄文句子导出为单独源文件，便于逐章翻译。
输出 build/zhsrc/chXX.txt，格式：
  # chXX | TitleRu (TitleZh)
  ## chXXpYY [N]
  00|<russian sentence>
  01|<russian sentence>
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
chapters = json.load(open(os.path.join(HERE, "_sentences.json"), encoding="utf-8"))
out = os.path.join(HERE, "zhsrc")
os.makedirs(out, exist_ok=True)
for ch in chapters:
    cid = ch["id"]
    lines = [f"# {cid} | {ch['title_ru']} ({ch['title_zh']})"]
    for p in ch["paras"]:
        pid = p["id"]
        lines.append(f"## {pid} [{len(p['sents'])}]")
        for si, s in enumerate(p["sents"]):
            lines.append(f"{si:02d}|{s}")
    open(os.path.join(out, cid + ".txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("wrote", len(chapters), "chapter source files to", out)
