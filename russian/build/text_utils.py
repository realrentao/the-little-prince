# -*- coding: utf-8 -*-
"""俄语句子切分 + 分词工具"""
import re

# 不该在其后断句的缩写
# 注意: 只放绝不会独立成词的缩写。"им"/"б" 是真实词（代词/语气词），
# 放进来会导致 "...не страшно ли им. И они..." 无法断句。
ABBR = {
    "г", "гг", "вв", "т", "д", "п", "др", "ул", "стр", "рис",
    "тыс", "млн", "млрд", "св", "напр", "см",
}

SENT_END = ".!?…"


def split_sentences(text: str):
    """把俄语段落切成句子。对话破折号 '—' 视为新句起点。"""
    t = re.sub(r"\s+", " ", text).strip()
    if not t:
        return []

    out = []
    buf = ""
    i = 0
    n = len(t)
    while i < n:
        ch = t[i]
        buf += ch

        if ch in SENT_END:
            # 吞掉连续的句末标点，如 "?!" "…" "!.."
            while i + 1 < n and t[i + 1] in SENT_END:
                i += 1
                buf += t[i]
            # 吞掉紧随的收尾引号/括号
            while i + 1 < n and t[i + 1] in "»\")":
                i += 1
                buf += t[i]

            nxt = t[i + 1] if i + 1 < n else ""
            nxt2 = t[i + 2] if i + 2 < n else ""

            if nxt == " ":
                # 缩写保护: "1935 г. и" —— 小写开头则不断句
                last_word = re.findall(r"([А-Яа-яЁёA-Za-z]+)\.$", buf)
                if last_word and last_word[0].lower() in ABBR:
                    i += 1
                    continue
                # 后面必须是大写字母 / 破折号 / 开引号 / 数字 才断句
                if nxt2 and (nxt2.isupper() or nxt2 in "—«\u2014\u2013(" or nxt2.isdigit()):
                    out.append(buf.strip())
                    buf = ""
                    i += 1  # 跳过空格
            elif nxt == "":
                out.append(buf.strip())
                buf = ""
        i += 1

    if buf.strip():
        out.append(buf.strip())

    # 合并过短的碎片（如单独的 "—" 或 1 个字符）到上一句
    merged = []
    for s in out:
        if merged and (len(s) <= 2 or not re.search(r"[А-Яа-яЁёA-Za-z]", s)):
            merged[-1] = merged[-1] + " " + s
        else:
            merged.append(s)
    return merged


WORD_RE = re.compile(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*|[A-Za-z]+|\d+|[^\sА-Яа-яЁёA-Za-z\d]+|\s+")
CYR_RE = re.compile(r"^[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*$")


def tokenize(sentence: str):
    """切成 token 列表: [{t: 文本, w: 是否俄语单词}]"""
    toks = []
    for m in WORD_RE.finditer(sentence):
        s = m.group(0)
        if s.isspace():
            toks.append({"t": " ", "w": False})
        else:
            toks.append({"t": s, "w": bool(CYR_RE.match(s))})
    return toks
