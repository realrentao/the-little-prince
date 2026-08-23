# -*- coding: utf-8 -*-
"""聚焦：单句点读句尾是否自动停止（排除测试等待不足的假阴性）"""
import traceback
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8791/"
LOG = "_test_stop.txt"
_lines = []


def log(*a):
    _lines.append(" ".join(str(x) for x in a))
    with open(LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines) + "\n")


def main():
    with sync_playwright() as pw:
        br = pw.chromium.launch(channel="msedge", headless=True,
                                args=["--autoplay-policy=no-user-gesture-required", "--mute-audio"])
        pg = br.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)

        pg.goto(URL, wait_until="load")
        pg.wait_for_selector(".sent", timeout=15000)
        pg.locator("#chapterNav a").nth(2).click()      # 章2（含 ch02p00）
        pg.wait_for_timeout(300)

        tgt = pg.evaluate("""() => {
          const B = window.__BOOK__;
          const groups = {};
          document.querySelectorAll('.sent:not(.no-audio)').forEach(e => {
            (groups[e.dataset.pid] = groups[e.dataset.pid] || []).push(+e.dataset.si);
          });
          let pid = null;
          for (const k in groups) if (groups[k].length >= 6) { pid = k; break; }
          const f = (p, s) => { for (const c of B.chapters) for (const x of c.paras)
            if (x.id === p) return x.sents[s].t; };
          return { pid, t1: f(pid, 1) };
        }""")
        pid, t1 = tgt["pid"], tgt["t1"]
        log(f"段落 {pid}  句1 区间={t1}")
        log(f"句1 时长(时间戳)={t1[1]-t1[0]}ms")

        sel = f'.sent[data-pid="{pid}"][data-si="1"]'
        pg.click(sel, position={"x": 12, "y": 8})
        # 等待足够久：时间戳时长 + 4 秒缓冲余量
        wait = (t1[1] - t1[0]) + 4500
        log(f"等待 {wait}ms 后检查是否自动停止...")
        pg.wait_for_timeout(wait)

        s = pg.evaluate("""() => {
          const a = document.getElementById('audio');
          return { paused: a.paused, ct: a.currentTime * 1000, dur: a.duration,
                   loop: document.getElementById('chkLoop').checked };
        }""")
        log(f"结果 paused={s['paused']}  ct={s['ct']:.0f}  duration={s['dur']:.0f}  loop={s['loop']}")

        if s["paused"]:
            # 停在句尾附近？（允许句尾静音余量 ±800）
            within = (t1[1] - 800) <= s["ct"] <= (t1[1] + 800)
            log("判定：✓ 句尾自动停止，且停在句尾附近" if within
                else f"判定：✓ 已停，但位置偏离句尾 (ct={s['ct']:.0f}, 句尾={t1[1]})")
        else:
            log(f"判定：✗ 未停止（仍在播放，ct={s['ct']:.0f}，已超句尾 {t1[1]}）")

        log("JS 报错：" + ("无" if not errs else "; ".join(errs[:5])))
        br.close()


try:
    main()
except Exception:
    log("\n!!! 异常 !!!\n" + traceback.format_exc())
