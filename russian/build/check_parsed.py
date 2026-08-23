# -*- coding: utf-8 -*-
"""检查解析结果：输出每章段落首句预览到 _inspect.txt"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(os.path.join(HERE, "_parsed.json"), encoding="utf-8"))

with open(os.path.join(HERE, "_inspect.txt"), "w", encoding="utf-8") as f:
    for i, c in enumerate(data):
        f.write(f"\n===== [{i:02d}] {c['title']}  (paras={len(c['paras'])}) =====\n")
        for j, p in enumerate(c["paras"]):
            preview = p[:110].replace("\n", " ")
            f.write(f"  {j:02d} ({len(p):>5} ch) {preview}\n")
print("ok")
