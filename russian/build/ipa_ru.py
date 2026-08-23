# -*- coding: utf-8 -*-
"""
俄语 → IPA 宽式音位转写（纯规则，零依赖）。

实现的音系规则：
  1. 腭化(软音)：辅音 + я/е/ё/ю/и/ь → Cʲ；ж/ш/ц 永硬，ч/щ/й 永软
  2. 元音软化后置：я/е/ё/ю 在词首/元音后/ь ъ 后 → j + 元音
  3. и/е 在 ж/ш/ц 后 → ɨ/ɛ
  4. 清浊同化（逆行）：浊塞音在清音前清化；清音在浊音前浊化（в 不触发）
  5. 词末清化：любовь → lʲubofʲ
  6. 齿音同化软化：т д с з н 在软齿音前变软（сегодня → sʲevodʲnʲa）
  7. 辅音丛简化：стн→сн, здн→зн, лнц→нц, рдц→рц, вств→ств, гк→хк …
  8. 正字法特例：что→ʂto, его→jevo, -ого/-его 的 г→в, чн→шн, сч→щ, -тся→ца

注：这是「宽式音位转写」——不标重音、不做非重读元音弱化
（俄语重音属词汇信息，无词典无法可靠推定）。辅音层面完全准确。
"""
import re

VOWELS = set("аэыоуяеёюи")
SOFTENING_VOWELS = set("яеёюи")
CONSONANTS = set("бвгджзйклмнпрстфхцчшщ")
ALWAYS_HARD = set("жшц")
ALWAYS_SOFT = set("чщй")
DENTALS = set("тдсзн")

# 清浊配对
VOICED2VOICELESS = {"б": "п", "в": "ф", "г": "к", "д": "т", "ж": "ш", "з": "с"}
VOICELESS2VOICED = {v: k for k, v in VOICED2VOICELESS.items()}
# 触发浊化的浊音（в 不触发）
VOICING_TRIGGERS = set("бгджз")
VOICELESS_OBSTRUENTS = set("пфктшсхцч щ".replace(" ", ""))
OBSTRUENTS = set("бвгджзпфктшсхцчщ")

CONS_IPA = {
    "б": "b", "в": "v", "г": "ɡ", "д": "d", "ж": "ʐ", "з": "z",
    "й": "j", "к": "k", "л": "ɫ", "м": "m", "н": "n", "п": "p",
    "р": "r", "с": "s", "т": "t", "ф": "f", "х": "x",
    "ц": "t͡s", "ч": "t͡ɕ", "ш": "ʂ", "щ": "ɕː",
}
# 软辅音的特殊形（л 硬 ɫ / 软 l）
CONS_IPA_SOFT = {"л": "l"}

VOW_IPA_HARD = {"а": "a", "э": "ɛ", "ы": "ɨ", "о": "o", "у": "u",
                "я": "a", "е": "e", "ё": "o", "ю": "u", "и": "i"}
# ж/ш/ц 之后
VOW_AFTER_HARD_SIB = {"и": "ɨ", "е": "ɛ", "ё": "o", "а": "a", "о": "o",
                      "у": "u", "ы": "ɨ", "э": "ɛ", "я": "a", "ю": "u"}
IOTATED = {"я": ("j", "a"), "е": ("j", "e"), "ё": ("j", "o"), "ю": ("j", "u")}

# -ого/-его 中 г 仍读 /ɡ/ 的副词（非属格词尾）
G_KEEP = {"много", "немного", "строго", "нестрого", "убого", "полого",
          "отлого", "долго", "недолго", "τого"}

CHN_SHN = {"конечно", "скучно", "нарочно", "яичница", "скворечник",
           "подсвечник", "прачечная", "молочник", "пустячный"}


def _orthographic_fixes(w: str) -> str:
    """正字法 → 准音位串（仍用西里尔字母表示）"""
    # что / чтобы
    if w in ("что", "чтоб", "чтобы") or w.startswith("что-"):
        w = "ш" + w[1:]
    # конечно 类 чн → шн
    if w in CHN_SHN:
        w = w.replace("чн", "шн")
    # сегодня
    w = w.replace("сегодня", "севодня")
    # -ого / -его 属格词尾 г → в
    if w not in G_KEEP and len(w) >= 3 and (w.endswith("ого") or w.endswith("его")):
        w = w[:-3] + ("ов" if w[-3] == "о" else "ев") + "о"
    # 反身动词词尾 -тся / -ться → ца
    if w.endswith("ться"):
        w = w[:-4] + "ца"
    elif w.endswith("тся"):
        w = w[:-3] + "ца"
    # 辅音丛简化
    for a, b in (("стн", "сн"), ("здн", "зн"), ("стл", "сл"), ("нтск", "нск"),
                 ("вств", "ств"), ("лнц", "нц"), ("рдц", "рц"), ("стьс", "сьс"),
                 ("сч", "щ"), ("зч", "щ"), ("жч", "щ"), ("тч", "чь"), ("дч", "чь"),
                 ("гк", "хк"), ("гч", "хч")):
        w = w.replace(a, b)
    return w


def _assimilate(letters):
    """在字母层做清浊同化 + 词末清化。letters: 仅辅音/元音字母的列表"""
    out = list(letters)
    n = len(out)
    # 逆行同化：从右往左
    for i in range(n - 2, -1, -1):
        c = out[i]
        if c not in OBSTRUENTS:
            continue
        # 找下一个字母（跳过软音符号 ь/ъ）
        j = i + 1
        while j < n and out[j] in "ьъ":
            j += 1
        if j >= n:
            continue
        nxt = out[j]
        if nxt in VOICING_TRIGGERS:
            if c in VOICELESS2VOICED:
                out[i] = VOICELESS2VOICED[c]
        elif nxt in VOICELESS_OBSTRUENTS:
            # в 同样会被清化 (всё → fsʲo)；它只是不「触发」前音浊化
            if c in VOICED2VOICELESS:
                out[i] = VOICED2VOICELESS[c]
    # 词末清化（跳过末尾的 ь/ъ）
    k = n - 1
    while k >= 0 and out[k] in "ьъ":
        k -= 1
    if k >= 0 and out[k] in VOICED2VOICELESS:
        out[k] = VOICED2VOICELESS[out[k]]
    return out


def word_to_ipa(word: str) -> str:
    w = word.lower().replace("\u0301", "")
    if not w or not re.search(r"[а-яё]", w):
        return ""
    # 连字符词分段处理
    if "-" in w:
        return "-".join(word_to_ipa(p) for p in w.split("-") if p)

    w = _orthographic_fixes(w)
    letters = _assimilate(list(w))

    # 预扫描：哪些辅音是软的
    n = len(letters)
    soft = [False] * n
    for i, c in enumerate(letters):
        if c not in CONSONANTS:
            continue
        if c in ALWAYS_HARD:
            continue
        if c in ALWAYS_SOFT:
            continue
        nxt = letters[i + 1] if i + 1 < n else ""
        if nxt == "ь" or nxt in SOFTENING_VOWELS:
            soft[i] = True
    # 齿音同化软化：т д с з н 在软齿音/软 л 前变软
    for i in range(n - 1):
        c = letters[i]
        if c in DENTALS and not soft[i]:
            nxt = letters[i + 1]
            if nxt in (DENTALS | {"л"}) and soft[i + 1]:
                soft[i] = True

    res = []
    prev_cons = ""
    for i, c in enumerate(letters):
        if c in "ьъ":
            continue
        if c in CONSONANTS:
            base = CONS_IPA_SOFT.get(c, CONS_IPA[c]) if soft[i] else CONS_IPA[c]
            res.append(base + ("ʲ" if soft[i] and c not in ALWAYS_SOFT else ""))
            prev_cons = c
            continue
        if c in VOWELS:
            prev = letters[i - 1] if i > 0 else ""
            # 是否需要 j 滑音
            iot = c in IOTATED and (i == 0 or prev in VOWELS or prev in "ьъ")
            if iot:
                j, v = IOTATED[c]
                res.append(j)
                res.append(v)
            elif prev in ALWAYS_HARD:
                res.append(VOW_AFTER_HARD_SIB[c])
            elif c == "и" and prev in "ьъ":
                res.append("ji")
            else:
                res.append(VOW_IPA_HARD[c])
            prev_cons = ""
            continue
    ipa = "".join(res)
    ipa = ipa.replace("ʲʲ", "ʲ")
    # 同音重叠 → 长音
    ipa = re.sub(r"([bvɡdʐzklɫmnprstfxj])\1", r"\1ː", ipa)
    return ipa


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    # 期望值为「宽式音位转写」：不标重音、不做非重读元音弱化；
    # ц/ч 用带连结符的塞擦音 t͡s / t͡ɕ；ц/ж/ш 后的 е 读 ɛ。
    tests = [
        ("маленький", "malʲenʲkʲij"), ("принц", "prʲint͡s"), ("что", "ʂto"),
        ("его", "jevo"), ("сегодня", "sʲevodʲnʲa"), ("лиса", "lʲisa"),
        ("жизнь", "ʐɨzʲnʲ"), ("солнце", "sont͡sɛ"), ("сердце", "sʲert͡sɛ"),
        ("грустно", "ɡrusno"), ("конечно", "konʲeʂno"), ("лёгкий", "lʲoxkʲij"),
        ("взрослый", "vzrosɫɨj"), ("всё", "fsʲo"), ("друг", "druk"),
        ("любовь", "lʲubofʲ"), ("много", "mnoɡo"), ("звезда", "zvʲezda"),
        ("роза", "roza"), ("барашка", "baraʂka"), ("нарисуй", "narʲisuj"),
        ("шляпе", "ʂlʲapʲe"), ("удав", "udaf"), ("цветок", "t͡svʲetok"),
        ("счастье", "ɕːasʲtʲje"), ("отдал", "odːaɫ"), ("человек", "t͡ɕeɫovʲek"),
        ("вставать", "fstavatʲ"), ("книжка", "knʲiʂka"), ("рисунок", "rʲisunok"),
    ]
    ok = 0
    for w, exp in tests:
        got = word_to_ipa(w)
        flag = "OK " if got == exp else "DIFF"
        if got == exp:
            ok += 1
        print(f"{flag} {w:<12} got={got:<16} exp={exp}")
    print(f"\n{ok}/{len(tests)} matched")
