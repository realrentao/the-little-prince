# -*- coding: utf-8 -*-
"""
从 _parsed.json 提取正文（献词 + 第1-27章），切句，输出:
  _sentences.json  —— 结构化数据
  _worksheet.txt   —— 供逐句翻译核对的工作表
"""
import json
import os
import sys

from text_utils import split_sentences

HERE = os.path.dirname(os.path.abspath(__file__))

# 正文范围：section index 02 (Посвящение) .. 29 (Глава 27)
BODY_START = 2
# 第27章只保留前 3 段（其后是后记/目录/版权页）
CH27_KEEP = 3

CH_TITLES_ZH = {
    "Посвящение": "献词",
}


def main():
    data = json.load(open(os.path.join(HERE, "_parsed.json"), encoding="utf-8"))
    body = []
    for idx in range(BODY_START, len(data)):
        sec = data[idx]
        paras = sec["paras"]
        if sec["title"].strip() == "Глава 27":
            paras = paras[:CH27_KEEP]
        body.append({"title": sec["title"], "paras": paras})

    chapters = []
    total_sent = 0
    total_chars = 0
    for ci, sec in enumerate(body):
        title = sec["title"].strip()
        if title.startswith("Глава"):
            num = title.split()[-1]
            zh = f"第 {num} 章"
        else:
            zh = CH_TITLES_ZH.get(title, title)
        ch = {"id": f"ch{ci:02d}", "title_ru": title, "title_zh": zh, "paras": []}
        for pi, p in enumerate(sec["paras"]):
            sents = split_sentences(p)
            total_sent += len(sents)
            total_chars += sum(len(s) for s in sents)
            ch["paras"].append({"id": f"ch{ci:02d}p{pi:02d}", "sents": sents})
        chapters.append(ch)

    json.dump(chapters, open(os.path.join(HERE, "_sentences.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    with open(os.path.join(HERE, "_worksheet.txt"), "w", encoding="utf-8") as f:
        for ch in chapters:
            f.write(f"\n########## {ch['id']} | {ch['title_ru']} ({ch['title_zh']}) ##########\n")
            for p in ch["paras"]:
                f.write(f"\n--- {p['id']}  [{len(p['sents'])} sents] ---\n")
                for si, s in enumerate(p["sents"]):
                    f.write(f"{si:02d}| {s}\n")

    # 统计
    with open(os.path.join(HERE, "_stats.txt"), "w", encoding="utf-8") as f:
        f.write(f"chapters: {len(chapters)}\n")
        f.write(f"paragraphs: {sum(len(c['paras']) for c in chapters)}\n")
        f.write(f"sentences: {total_sent}\n")
        f.write(f"ru chars: {total_chars}\n\n")
        for ch in chapters:
            ns = sum(len(p["sents"]) for p in ch["paras"])
            nc = sum(len(s) for p in ch["paras"] for s in p["sents"])
            f.write(f"{ch['id']}  {ch['title_ru']:<12} paras={len(ch['paras']):>2} sents={ns:>4} chars={nc:>6}\n")
    print("ok")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
