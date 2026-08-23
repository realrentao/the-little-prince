# -*- coding: utf-8 -*-
"""
Wrap illustrations/placement.json as data/illust.js (a JS global).
"""
import os, json
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SRC  = os.path.join(ROOT, "illustrations", "placement.json")
DST  = os.path.join(ROOT, "data", "illust.js")
data = json.load(open(SRC, encoding="utf-8"))
js = "/* Auto-generated illustration placement map. */\n"
js += "window.__ILLUST__ = " + json.dumps(data, ensure_ascii=False) + ";\n"
open(DST, "w", encoding="utf-8").write(js)
print("Wrote", DST, len(data), "entries")
