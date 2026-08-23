# -*- coding: utf-8 -*-
"""
E2E test: navigate to ch01 and ch21, take screenshots to verify illustration
rendering, alignment, and responsiveness.
"""
import os, sys, traceback
LOG = r"D:\workbuddy工作区\2026-08-23-21-28-02\little-prince-ru\build\_illust_test.txt"
def log(*a):
    msg = " ".join(str(x) for x in a)
    print(msg)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        # 1) Desktop
        b = pw.chromium.launch(channel="msedge", headless=True, args=["--mute-audio"])
        ctx = b.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        errs = []
        page.on("console", lambda m: errs.append(m.type + ": " + m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
        page.goto("http://127.0.0.1:8791/", wait_until="load")
        page.wait_for_selector(".sent", timeout=15000)
        # ch01 is index 0 in the chapter nav; click it
        # The nav links have text matching chapter titles; easier: query nav
        # by chapter id
        log("title:", page.title())
        # Click first chapter link
        nav = page.query_selector_all("#chapterNav a")
        log("nav items:", len(nav))
        # ch01 is index 1 (0 = Посвящение preface)
        nav[1].dispatch_event("click")
        page.wait_for_selector(".illust-header img", timeout=8000)
        # Wait for the actual image to be loaded
        page.wait_for_function("Array.from(document.querySelectorAll('.illust-header img')).every(i => i.complete && i.naturalWidth>0)", timeout=10000)
        page.wait_for_timeout(300)  # let layout settle
        log("ch01 header illust loaded; src=", page.eval_on_selector(".illust-header img", "e => e.src.split('/').slice(-2).join('/')"))
        page.screenshot(path=r"D:\workbuddy工作区\2026-08-23-21-28-02\little-prince-ru\_shot_ch01_desktop.png", full_page=False)
        log("saved _shot_ch01_desktop.png")
        # Switch to ch21 (Притча о Лисе) -> index 21 in nav (ch00=0,ch01=1,...)
        nav[21].dispatch_event("click")
        page.wait_for_selector(".illust-header img", timeout=8000)
        page.wait_for_function("Array.from(document.querySelectorAll('.illust-header img')).every(i => i.complete && i.naturalWidth>0)", timeout=10000)
        # Scroll to header for screenshot
        page.eval_on_selector(".illust-header", "e => e.scrollIntoView({block:'start'})")
        page.wait_for_timeout(300)
        log("ch21 header illust loaded; src=", page.eval_on_selector(".illust-header img", "e => e.src.split('/').slice(-2).join('/')"))
        page.screenshot(path=r"D:\workbuddy工作区\2026-08-23-21-28-02\little-prince-ru\_shot_ch21_desktop.png", full_page=False)
        log("saved _shot_ch21_desktop.png")
        # Count inline illustrations on this page
        inlines = page.query_selector_all(".illust-inline")
        log("ch21 inline illusts:", len(inlines))
        # 2) Mobile
        ctx2 = b.new_context(viewport={"width": 390, "height": 800}, device_scale_factor=2)
        page2 = ctx2.new_page()
        page2.goto("http://127.0.0.1:8791/", wait_until="load")
        page2.wait_for_selector(".sent", timeout=15000)
        nav2 = page2.query_selector_all("#chapterNav a")
        nav2[1].dispatch_event("click")
        page2.wait_for_selector(".illust-header img", timeout=8000)
        page2.wait_for_function("Array.from(document.querySelectorAll('.illust-header img')).every(i => i.complete && i.naturalWidth>0)", timeout=10000)
        page2.wait_for_timeout(300)
        page2.wait_for_selector(".illust-header img", timeout=8000)
        page2.screenshot(path=r"D:\workbuddy工作区\2026-08-23-21-28-02\little-prince-ru\_shot_ch01_mobile.png", full_page=False)
        log("saved _shot_ch01_mobile.png")
        b.close()
        log("--- errors:", errs)
except Exception:
    traceback.print_exc()
    with open(LOG, "a", encoding="utf-8") as f:
        traceback.print_exc(file=f)
    raise
