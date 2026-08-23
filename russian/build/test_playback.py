# -*- coding: utf-8 -*-
"""点读 / 打断机制端到端测试（Playwright + 系统 Edge）"""
import sys, json, traceback
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8791/"
LOG = "_test_out.txt"
results = []
_lines = []


def print(*a):                                    # noqa: A001 - 覆盖为写文件版
    _lines.append(" ".join(str(x) for x in a))
    with open(LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines) + "\n")


def ok(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("  PASS  " if cond else "  FAIL  ") + name + ("   " + detail if detail else ""))


AUDIO_STATE = """() => {
  const a = document.getElementById('audio');
  const solo = document.querySelector('.sent.solo');
  return {
    paused: a.paused, ct: a.currentTime * 1000, dur: a.duration,
    src: (a.currentSrc || '').split('/').pop(),
    rate: a.playbackRate,
    soloCount: document.querySelectorAll('.sent.solo').length,
    soloPid: solo ? solo.dataset.pid : null,
    soloSi: solo ? +solo.dataset.si : null,
    activeCount: document.querySelectorAll('.sent.active').length,
    nowSub: (document.getElementById('nowSub') || {}).textContent || ''
  };
}"""


def main():
    with sync_playwright() as pw:
        br = pw.chromium.launch(
            channel="msedge", headless=True,
            args=["--autoplay-policy=no-user-gesture-required", "--mute-audio"],
        )
        pg = br.new_page(viewport={"width": 1440, "height": 900})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append("console." + m.type + ": " + m.text)
              if (m.type == "error" and "favicon" not in m.text and "404" not in m.text)
              else None)

        pg.goto(URL, wait_until="load")
        pg.wait_for_selector(".sent", timeout=15000)

        # 换到句子较多的一章
        pg.locator("#chapterNav a").nth(2).click()
        pg.wait_for_timeout(300)

        tgt = pg.evaluate("""() => {
          const B = window.__BOOK__;
          const find = (pid, si) => {
            for (const c of B.chapters) for (const p of c.paras)
              if (p.id === pid) return p.sents[si];
          };
          // 取同一段落内、有时间戳的前若干句
          const groups = {};
          document.querySelectorAll('.sent:not(.no-audio)').forEach(e => {
            (groups[e.dataset.pid] = groups[e.dataset.pid] || []).push(+e.dataset.si);
          });
          let pid = null;
          for (const k in groups) if (groups[k].length >= 6) { pid = k; break; }
          if (!pid) return null;
          const a = 1, b = 4;
          return { pid, a, b, ta: find(pid, a).t, tb: find(pid, b).t,
                   tnext: find(pid, b + 1).t, n: groups[pid].length };
        }""")
        assert tgt, "找不到 >=6 句的段落"
        pid, ia, ib = tgt["pid"], tgt["a"], tgt["b"]
        ta, tb, tnext = tgt["ta"], tgt["tb"], tgt["tnext"]
        print(f"测试段落 {pid}（{tgt['n']} 句）  句{ia} t={ta}  句{ib} t={tb}")

        sel = lambda si: f'.sent[data-pid="{pid}"][data-si="{si}"]'
        # 点左侧空白，避免命中悬停浮现的操作按钮
        LEFT = {"x": 12, "y": 8}

        # ---------- 1. 单句点读：只播这一句 ----------
        print("\n[1] 单句点读 —— 点某句只播这一句")
        pg.click(sel(ia), position=LEFT)
        pg.wait_for_timeout(500)
        s = pg.evaluate(AUDIO_STATE)
        ok("点击后开始播放", not s["paused"], f"paused={s['paused']}")
        ok("音频文件正确", s["src"] == pid + ".mp3", s["src"])
        ok("从该句起点开始", abs(s["ct"] - ta[0]) < 900, f"ct={s['ct']:.0f} 期望≈{ta[0]}")
        ok("该句标记为 solo", s["soloCount"] == 1 and s["soloPid"] == pid
           and s["soloSi"] == ia, f"solo={s['soloPid']}#{s['soloSi']}")
        ok("状态栏显示单句点读", "单句点读" in s["nowSub"], s["nowSub"])

        # 等到该句结束 + 缓冲（edge-tts 实际音频比时间戳稍长，含句尾静音余量）
        pg.wait_for_timeout(int(ta[1] - ta[0]) + 3800)
        s = pg.evaluate(AUDIO_STATE)
        ok("句尾自动停止（不续读全文）", s["paused"], f"paused={s['paused']}")
        ok("停在句尾附近", ta[1] - 200 <= s["ct"] <= ta[1] + 900,
           f"ct={s['ct']:.0f} 句尾={ta[1]}")

        # ---------- 2. 打断机制 ----------
        print("\n[2] 打断机制 —— 播新音频时旧音频立刻停止")
        pg.click(sel(ia), position=LEFT)
        pg.wait_for_timeout(250)
        mid = pg.evaluate(AUDIO_STATE)
        pg.click(sel(ib), position=LEFT)        # 播放中立刻点另一句
        pg.wait_for_timeout(500)
        s = pg.evaluate(AUDIO_STATE)
        ok("旧句播放中被打断", not mid["paused"], f"打断前 paused={mid['paused']}")
        ok("已跳到新句起点", abs(s["ct"] - tb[0]) < 900, f"ct={s['ct']:.0f} 期望≈{tb[0]}")
        ok("solo 唯一且已转移", s["soloCount"] == 1 and s["soloSi"] == ib,
           f"count={s['soloCount']} si={s['soloSi']}")
        ok("高亮句唯一", s["activeCount"] == 1, f"active={s['activeCount']}")
        ok("无 JS 报错", not errs, "; ".join(errs[:3]))

        # 快速连点 5 句：不应叠音 / 不应残留旧回调
        print("\n[2b] 快速连点 5 句（跨段落）")
        allsents = pg.evaluate("""() => [...document.querySelectorAll('.sent:not(.no-audio)')]
            .slice(0, 40).map(e => [e.dataset.pid, +e.dataset.si])""")
        picks = [allsents[i] for i in (0, 9, 3, 20, 12) if i < len(allsents)]
        for p2, s2 in picks:
            pg.click(f'.sent[data-pid="{p2}"][data-si="{s2}"]', position=LEFT)
            pg.wait_for_timeout(120)
        pg.wait_for_timeout(700)
        s = pg.evaluate(AUDIO_STATE)
        last_pid, last_si = picks[-1]
        exp = pg.evaluate("""(o) => {
          const B = window.__BOOK__;
          for (const c of B.chapters) for (const p of c.paras)
            if (p.id === o.pid) return p.sents[o.si].t;
        }""", {"pid": last_pid, "si": last_si})
        ok("只保留最后一次点击", s["soloPid"] == last_pid and s["soloSi"] == last_si,
           f"solo={s['soloPid']}#{s['soloSi']} 期望={last_pid}#{last_si}")
        ok("音频落在最后那句", s["src"] == last_pid + ".mp3"
           and abs(s["ct"] - exp[0]) < 1200, f"src={s['src']} ct={s['ct']:.0f} 期望≈{exp[0]}")
        ok("连点后无 JS 报错", not errs, "; ".join(errs[:3]))

        # ---------- 3. Shift+单击 = 从此连读 ----------
        print("\n[3] Shift+单击 —— 从该句往下连读")
        pg.click(sel(ib), position=LEFT, modifiers=["Shift"])
        pg.wait_for_timeout(400)
        s = pg.evaluate(AUDIO_STATE)
        ok("连读模式无 solo 标记", s["soloCount"] == 0, f"soloCount={s['soloCount']}")
        pg.wait_for_timeout(int(tb[1] - tb[0]) + 1200)
        s = pg.evaluate(AUDIO_STATE)
        ok("越过句尾继续朗读", (not s["paused"]) and s["ct"] > tb[1],
           f"paused={s['paused']} ct={s['ct']:.0f} > 句尾{tb[1]}")

        # ---------- 4. 单句循环 ----------
        print("\n[4] 单句循环")
        pg.evaluate("() => document.getElementById('audio').pause()")
        pg.check("#chkLoop")
        pg.click(sel(ia), position=LEFT)
        pg.wait_for_timeout(int(ta[1] - ta[0]) + 1400)   # 已过句尾
        s = pg.evaluate(AUDIO_STATE)
        ok("过句尾仍在播（已循环）", not s["paused"], f"paused={s['paused']}")
        ok("时间回到本句区间内", ta[0] - 200 <= s["ct"] <= ta[1] + 300,
           f"ct={s['ct']:.0f} 区间=[{ta[0]},{ta[1]}]")
        pg.uncheck("#chkLoop")

        # ---------- 5. 上一句 / 下一句 / 重复本句 ----------
        print("\n[5] 上一句 / 下一句 / 重复本句")
        pg.click(sel(ia), position=LEFT)
        pg.wait_for_timeout(300)
        pg.click("#btnNextSent")
        pg.wait_for_timeout(450)
        s = pg.evaluate(AUDIO_STATE)
        ok("下一句 → si+1", s["soloSi"] == ia + 1, f"si={s['soloSi']}")
        pg.click("#btnPrevSent")
        pg.wait_for_timeout(450)
        s = pg.evaluate(AUDIO_STATE)
        ok("上一句 → si-1", s["soloSi"] == ia, f"si={s['soloSi']}")
        pg.wait_for_timeout(int(ta[1] - ta[0]) + 900)     # 让它自然停
        pg.click("#btnRepeat")
        pg.wait_for_timeout(450)
        s = pg.evaluate(AUDIO_STATE)
        ok("重复本句重新播放", (not s["paused"]) and abs(s["ct"] - ta[0]) < 900,
           f"paused={s['paused']} ct={s['ct']:.0f}")

        # ---------- 6. 键盘快捷键 ----------
        print("\n[6] 快捷键 → / ← / R / 空格")
        pg.keyboard.press("ArrowRight")
        pg.wait_for_timeout(420)
        s = pg.evaluate(AUDIO_STATE)
        ok("→ 下一句", s["soloSi"] == ia + 1, f"si={s['soloSi']}")
        pg.keyboard.press("ArrowLeft")
        pg.wait_for_timeout(420)
        s = pg.evaluate(AUDIO_STATE)
        ok("← 上一句", s["soloSi"] == ia, f"si={s['soloSi']}")
        pg.keyboard.press("Space")
        pg.wait_for_timeout(280)
        s = pg.evaluate(AUDIO_STATE)
        ok("空格暂停", s["paused"], f"paused={s['paused']}")

        # ---------- 7. 语速 + 段落朗读回归 ----------
        print("\n[7] 回归：语速 / 段落朗读 / 拖动退出点读")
        pg.eval_on_selector("#rate", "el => { el.value = 1.6; el.dispatchEvent(new Event('input')); }")
        pg.click(sel(ia), position=LEFT)
        pg.wait_for_timeout(400)
        s = pg.evaluate(AUDIO_STATE)
        ok("语速 1.60× 生效", abs(s["rate"] - 1.6) < 0.02, f"rate={s['rate']}")
        pg.eval_on_selector("#rate", "el => { el.value = 1; el.dispatchEvent(new Event('input')); }")

        pg.click(f'.para[data-pid="{pid}"] .para-play')
        pg.wait_for_timeout(500)
        s = pg.evaluate(AUDIO_STATE)
        ok("段落朗读从 0 开始", s["ct"] < 800 and not s["paused"], f"ct={s['ct']:.0f}")
        ok("段落朗读清除 solo", s["soloCount"] == 0, f"soloCount={s['soloCount']}")

        pg.click(sel(ia), position=LEFT)
        pg.wait_for_timeout(300)
        pg.eval_on_selector("#seek", "el => { el.value = 500; el.dispatchEvent(new Event('change')); }")
        pg.wait_for_timeout(200)
        s = pg.evaluate(AUDIO_STATE)
        ok("拖动进度条退出点读", s["soloCount"] == 0, f"soloCount={s['soloCount']}")

        ok("全程无 JS 报错", not errs, "; ".join(errs[:5]))

        pg.screenshot(path="../_shot_reader.png", full_page=False)
        br.close()

    n_pass = sum(1 for _, c, _ in results if c)
    print("\n" + "=" * 58)
    print(f"结果：{n_pass} / {len(results)} 通过")
    bad = [n for n, c, d in results if not c]
    if bad:
        print("失败项：")
        for b in bad:
            print("  - " + b)
    else:
        print("全部通过 ✓")


try:
    main()
except Exception:
    print("\n!!! 测试脚本异常 !!!")
    print(traceback.format_exc())
