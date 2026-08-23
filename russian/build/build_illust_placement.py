# -*- coding: utf-8 -*-
"""
Build the illustration-to-chapter placement map.

For each illustration in illustrations/_catalog.json:
  1) Decide which chapter it belongs to (ch00..ch27, ch00 = preface).
  2) Filter out obvious non-illustrations (logos, small decorations).
  3) Decide its insert position: chapter start (in chapter header) vs.
     mid-chapter (after roughly proportional sentence offset).
  4) Output illustrations/placement.json with one entry per insertion:
       {file, chapter, after_sentence_idx, kind, label}
"""
import os, json, re
from PIL import Image

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ILL  = os.path.join(ROOT, "illustrations")

# ch00 = preface (cover/intro before ch01)
# ch01..ch27 = real chapters, mapped to PDF pages below
CH_PAGES = {
    0: 0,    # preface: cover + intro
    1: 7,    2: 10,   3: 16,   4: 19,   5: 25,   6: 30,   7: 32,
    8: 36,   9: 42,  10: 46,  11: 52,  12: 55,  13: 57,  14: 62,
    15: 66, 16: 70,  17: 71,  18: 75,  19: 76,  20: 78,  21: 80,
    22: 87,  23: 89,  24: 90,  25: 93,  26: 98,  27: 106,
}
# ch28 is the appendix (variants of drawings)
APPENDIX_START = 112

catalog = json.load(open(os.path.join(ILL, "_catalog.json"), encoding="utf-8"))

def page_to_chapter(pdf_page):
    if pdf_page < CH_PAGES[1]:
        return 0  # preface
    if pdf_page >= APPENDIX_START:
        return 28  # appendix
    for ch in range(27, 0, -1):
        if pdf_page >= CH_PAGES[ch]:
            return ch
    return 0

def is_decoration(entry):
    """Filter small/logo-like images by image dimensions (post-trim)."""
    try:
        with Image.open(os.path.join(ILL, entry["file"])) as im:
            w, h = im.size
    except Exception:
        return True
    # After trim, a "real illustration" is at least ~200x200. Small/flat ones
    # (logos, chapter headers, page ornaments) are excluded.
    if w < 240 or h < 240:
        return True
    # very wide or very tall, very thin ratio -> ornament
    if max(w, h) / max(1, min(w, h)) > 6:
        return True
    return False

# Group by (pdf_page, xref) to dedupe
seen = set()
filtered = []
for e in catalog:
    key = (e["pdf_page"], e.get("xref", -1))
    if key in seen: continue
    seen.add(key)
    if is_decoration(e):
        continue
    filtered.append(e)

# Now build per-chapter list with position
chapter_illusts = {ch: [] for ch in range(0, 29)}
for e in filtered:
    ch = page_to_chapter(e["pdf_page"])
    if ch == 28:
        # appendix -> no placement
        continue
    chapter_illusts[ch].append(e)

# For each chapter, decide which illustration goes to chapter-header (first
# big one near the chapter start) and the rest go in-text.
# A 'chapter header' illustration: pdf_page within 1 of CH_PAGES[ch].
placement = []
for ch, items in chapter_illusts.items():
    if not items: continue
    # sort by pdf_page
    items.sort(key=lambda x: (x["pdf_page"], x.get("xref", 0)))
    # find first 'near chapter start' (within +1 page) -> header
    header_done = False
    for it in items:
        if not header_done and abs(it["pdf_page"] - CH_PAGES.get(ch, 0)) <= 1 and ch > 0:
            placement.append({
                "file": it["file"],
                "chapter": ch,
                "position": "header",
                "after_sentence": 0,  # before any sentence of that chapter
            })
            header_done = True
        else:
            placement.append({
                "file": it["file"],
                "chapter": ch,
                "position": "inline",
                "pdf_page": it["pdf_page"],
            })

# Compute "after_sentence" for in-text illustrations by proportional
# distribution within the chapter.
sentences_per_ch = json.load(open(os.path.join(ROOT, "data", "book.json"), encoding="utf-8"))
# build per-chapter sentence index spans
ch_sents = {}
for c in sentences_per_ch["chapters"]:
    ch_sents[c["id"]] = sum(len(p["sents"]) for p in c["paras"])

ch_pdf_range = {}
sorted_chs = sorted(CH_PAGES.keys())
for i, ch in enumerate(sorted_chs):
    start = CH_PAGES[ch]
    end = CH_PAGES[sorted_chs[i+1]] - 1 if i+1 < len(sorted_chs) else APPENDIX_START - 1
    ch_pdf_range[ch] = (start, end)

# for in-text: distribute by (pdf_page - ch_start) / (ch_end - ch_start)
for p in placement:
    if p["position"] != "inline": continue
    ch = p["chapter"]
    if ch not in ch_pdf_range: continue
    start, end = ch_pdf_range[ch]
    if end <= start:
        p["after_sentence"] = 0; continue
    n = ch_sents.get(f"ch{ch:02d}", 0)
    if n == 0:
        p["after_sentence"] = 0; continue
    frac = (p["pdf_page"] - start) / (end - start + 1)
    idx = min(n - 1, max(0, int(frac * n)))
    p["after_sentence"] = idx

with open(os.path.join(ILL, "placement.json"), "w", encoding="utf-8") as f:
    json.dump(placement, f, ensure_ascii=False, indent=2)
print(f"placement: {len(placement)} entries")
for p in placement[:8]:
    print(" ", p)
print(" ...")
for p in placement[-6:]:
    print(" ", p)
