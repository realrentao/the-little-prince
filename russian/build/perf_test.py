import sys, json, traceback
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8795/index.html"
OUT = "build/perf_report.json"
LOG = open("build/perf_test.log", "w", encoding="utf-8")

def main():
    rep = {}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(channel="msedge", args=["--autoplay-policy=no-user-gesture-required"])
            pg = b.new_page(viewport={"width": 1280, "height": 900})
            img_formats = {}
            def on_response(resp):
                n = resp.request.url
                if "/illustrations" in n:
                    ext = n.rsplit(".", 1)[-1].lower()
                    img_formats[ext] = img_formats.get(ext, 0) + 1
            pg.on("response", on_response)
            pg.goto(URL, wait_until="load")
            pg.wait_for_timeout(1500)
            loaded = pg.evaluate("""() => {
                const imgs=[...document.querySelectorAll('.illust img')];
                return {total:imgs.length, loaded:imgs.filter(i=>i.complete&&i.naturalWidth>0).map(i=>i.currentSrc)};
            }""")
            rep["first_screen_header_imgs_loaded"] = len(loaded["loaded"])
            rep["first_screen_total_illust_imgs_in_dom"] = loaded["total"]
            rep["img_response_formats_first_screen"] = dict(img_formats)
            pg.evaluate("""() => {
                const nav=[...document.querySelectorAll('#chapterNav a')];
                if(nav[4]) nav[4].click();
            }""")
            pg.wait_for_timeout(1200)
            ch5 = pg.evaluate("""() => {
                const imgs=[...document.querySelectorAll('.illust img')];
                return {total:imgs.length, loaded:imgs.filter(i=>i.complete&&i.naturalWidth>0).length,
                        srcs:imgs.map(i=>i.currentSrc)};
            }""")
            rep["ch5_illust_total"] = ch5["total"]
            rep["ch5_illust_loaded"] = ch5["loaded"]
            rep["ch5_srcs_sample"] = ch5["srcs"][:3]
            rep["img_response_formats_all"] = dict(img_formats)
            b.close()
            with open(OUT, "w", encoding="utf-8") as f:
                json.dump(rep, f, ensure_ascii=False, indent=2)
            print(json.dumps(rep, ensure_ascii=False, indent=2), file=LOG, flush=True)
    except Exception:
        traceback.print_exc(file=LOG)

if __name__ == "__main__":
    main()
