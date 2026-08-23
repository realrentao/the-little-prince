# -*- coding: utf-8 -*-
"""
组装 data/book.json + data/lexicon.json
  - 章节 / 段落 / 句子（俄 + 中）
  - 每句在段落音频中的毫秒区间（由 edge-tts WordBoundary 对齐得出）
  - 全书唯一词 → IPA 词典
"""
import json
import os
import re
import sys

from ipa_ru import word_to_ipa

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
AUDIO = os.path.join(ROOT, "audio")
DATA = os.path.join(ROOT, "data")
ZH = os.path.join(HERE, "zh")
os.makedirs(DATA, exist_ok=True)
os.makedirs(ZH, exist_ok=True)

WORD_RE = re.compile(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*")


def norm_word(s: str) -> str:
    return re.sub(r"[^а-яёa-z0-9]", "", s.lower().replace("ё", "ё"))


def align_timings(sents, events):
    """把 WordBoundary 事件对齐到句子，返回每句 (start_ms, end_ms)"""
    if not events:
        return [None] * len(sents)

    expected = []  # (sent_idx, norm_word)
    for si, s in enumerate(sents):
        for w in WORD_RE.findall(s):
            expected.append((si, norm_word(w)))

    assign = []  # 每个 event 对应的 sent_idx
    ptr = 0
    for e in events:
        et = norm_word(e["t"])
        placed = False
        if ptr < len(expected) and expected[ptr][1] == et:
            assign.append(expected[ptr][0])
            ptr += 1
            placed = True
        else:
            # 向前找 4 个（应对切句差异）
            for k in range(ptr + 1, min(ptr + 5, len(expected))):
                if expected[k][1] == et:
                    assign.append(expected[k][0])
                    ptr = k + 1
                    placed = True
                    break
        if not placed:
            # 数字被读成多个词等情况：归到当前句，不推进指针
            assign.append(expected[min(ptr, len(expected) - 1)][0])

    spans = [None] * len(sents)
    for si in range(len(sents)):
        idxs = [i for i, a in enumerate(assign) if a == si]
        if not idxs:
            continue
        st = min(events[i]["s"] for i in idxs)
        en = max(events[i]["s"] + events[i]["d"] for i in idxs)
        spans[si] = [st, en]

    # 补空洞：用前后邻居插值
    for si in range(len(sents)):
        if spans[si] is None:
            prev_end = next((spans[j][1] for j in range(si - 1, -1, -1) if spans[j]), 0)
            nxt_start = next((spans[j][0] for j in range(si + 1, len(sents)) if spans[j]), prev_end + 500)
            spans[si] = [prev_end, max(nxt_start, prev_end + 200)]
    # 单调化，并让每句结束点延伸到下一句开始（避免尾音被切）
    for si in range(len(sents) - 1):
        if spans[si + 1][0] > spans[si][1]:
            spans[si][1] = spans[si + 1][0]
    return spans


def main():
    chapters = json.load(open(os.path.join(HERE, "_sentences.json"), encoding="utf-8"))

    # 载入中文翻译
    zh_map = {}
    for fn in sorted(os.listdir(ZH)):
        if fn.endswith(".json"):
            try:
                zh_map.update(json.load(open(os.path.join(ZH, fn), encoding="utf-8")))
            except Exception as e:
                print(f"WARN bad zh file {fn}: {e}")

    lexicon = {}
    out_chapters = []
    problems = []
    n_sent = n_zh = 0
    audio_missing = 0

    for ch in chapters:
        out_paras = []
        for p in ch["paras"]:
            pid = p["id"]
            sents = p["sents"]

            # 音频时间戳
            js = os.path.join(AUDIO, f"{pid}.json")
            mp3 = os.path.join(AUDIO, f"{pid}.mp3")
            has_audio = os.path.exists(mp3) and os.path.getsize(mp3) > 2000
            events = []
            if os.path.exists(js):
                try:
                    events = json.load(open(js, encoding="utf-8"))
                except Exception:
                    events = []
            if not has_audio:
                audio_missing += 1

            # 中文
            zh_list = zh_map.get(pid)

            # 构建 (ru, zh) 配对，并合并同一段落内被源文件换行截断的单词
            # （如 "оде-" + "ваться" -> "одеваться"）。跨段落的截断因音频按段落
            # 生成、无法跨文件拼接，故保留原样。
            pairs = []
            for si, s in enumerate(sents):
                z = (zh_list[si] if zh_list else "")
                pairs.append([s, z])
            merged = []
            i = 0
            while i < len(pairs):
                ru, z = pairs[i]
                if re.search(r"[-­\u2010\u2011]\s*$", ru) and i + 1 < len(pairs):
                    nru, nz = pairs[i + 1]
                    ru = re.sub(r"[-­\u2010\u2011]\s*$", "", ru) + nru
                    z = z + nz
                    i += 2
                    merged.append([ru, z])
                else:
                    merged.append([ru, z])
                    i += 1

            merged_rus = [m[0] for m in merged]
            spans = align_timings(merged_rus, events)

            if zh_list is not None and len(zh_list) != len(sents):
                problems.append(f"{pid}: zh={len(zh_list)} != ru={len(sents)}")

            out_sents = []
            for si, (ru, z) in enumerate(merged):
                n_sent += 1
                if z:
                    n_zh += 1
                out_sents.append({"ru": ru, "zh": z, "t": spans[si]})
                for w in WORD_RE.findall(ru):
                    lw = w.lower()
                    if lw not in lexicon:
                        lexicon[lw] = word_to_ipa(lw)

            out_paras.append({"id": pid, "audio": has_audio, "sents": out_sents})
        out_chapters.append({
            "id": ch["id"], "title_ru": ch["title_ru"], "title_zh": ch["title_zh"],
            "paras": out_paras,
        })

    # 跨段落断词合并（仅修显示）：源文件换行把单词截断在段尾，续接部分在下段首句。
    # 音频按段落生成、无法跨文件拼接，故合并句以“续接段落”的音频起点为准播放。
    for ch in out_chapters:
        for pi in range(len(ch["paras"]) - 1):
            A = ch["paras"][pi]
            B = ch["paras"][pi + 1]
            if not A["sents"] or not B["sents"]:
                continue
            last = A["sents"][-1]
            if re.search(r"[-­\u2010\u2011]\s*$", last["ru"]):
                core = re.sub(r"[-­\u2010\u2011]\s*$", "", last["ru"])
                B["sents"][0]["ru"] = core + B["sents"][0]["ru"]
                B["sents"][0]["zh"] = (last["zh"] or "") + (B["sents"][0]["zh"] or "")
                for w in WORD_RE.findall(B["sents"][0]["ru"]):
                    lw = w.lower()
                    if lw not in lexicon:
                        lexicon[lw] = word_to_ipa(lw)
                A["sents"].pop()
                n_sent -= 1
                if last["zh"]:
                    n_zh -= 1

    book = {
        "meta": {
            "title_ru": "Маленький принц",
            "title_zh": "小王子",
            "author_ru": "Антуан де Сент-Экзюпери",
            "author_zh": "安托万·德·圣埃克苏佩里",
            "voice": "ru-RU-SvetlanaNeural (edge-tts)",
            "ipa_note": "宽式音位转写：标注辅音腭化/清浊同化/词末清化，不标重音、不做非重读元音弱化",
            "n_chapters": len(out_chapters),
            "n_paras": sum(len(c["paras"]) for c in out_chapters),
            "n_sents": n_sent,
        },
        "chapters": out_chapters,
    }
    json.dump(book, open(os.path.join(DATA, "book.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    json.dump(lexicon, open(os.path.join(DATA, "lexicon.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))

    # 同时输出 JS 包装版，使站点在 file:// 下双击即可打开（fetch 会被 CORS 拦）
    with open(os.path.join(DATA, "book.js"), "w", encoding="utf-8") as f:
        f.write("window.__BOOK__=")
        json.dump(book, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";")
    with open(os.path.join(DATA, "lexicon.js"), "w", encoding="utf-8") as f:
        f.write("window.__LEX__=")
        json.dump(lexicon, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";")

    with open(os.path.join(HERE, "_gen_report.txt"), "w", encoding="utf-8") as f:
        f.write(f"chapters      : {len(out_chapters)}\n")
        f.write(f"paragraphs    : {book['meta']['n_paras']}\n")
        f.write(f"sentences     : {n_sent}\n")
        f.write(f"zh translated : {n_zh}  ({n_zh*100//max(n_sent,1)}%)\n")
        f.write(f"lexicon words : {len(lexicon)}\n")
        f.write(f"audio missing : {audio_missing} paragraphs\n")
        f.write(f"book.json     : {os.path.getsize(os.path.join(DATA,'book.json'))//1024} KB\n")
        f.write(f"lexicon.json  : {os.path.getsize(os.path.join(DATA,'lexicon.json'))//1024} KB\n")
        if problems:
            f.write("\n!! COUNT MISMATCH !!\n")
            for x in problems:
                f.write("  " + x + "\n")
        else:
            f.write("\nno zh/ru count mismatch\n")
    print("done")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
