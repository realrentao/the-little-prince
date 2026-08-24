import glob, os, sys, traceback
from PIL import Image

LOG = open("build/compress_webp.log", "w", encoding="utf-8")
def log(*a):
    print(*a, file=LOG, flush=True)

def main_run():
    src_dir = "illustrations"
    out_dir = "illustrations-webp"
    os.makedirs(out_dir, exist_ok=True)

    files = sorted(glob.glob(os.path.join(src_dir, "*.png")))
    total_in = total_out = 0
    max_w = 1600
    header_w = 1080
    quality = 82
    errors = []

    for f in files:
        base = os.path.splitext(os.path.basename(f))[0]
        out = os.path.join(out_dir, base + ".webp")
        try:
            im = Image.open(f).convert("RGBA")
            w, h = im.size
            limit = header_w if ("_x" in base and int(base.split("_x")[-1]) < 100) else max_w
            if w > limit:
                scale = limit / w
                im = im.resize((limit, max(1, int(h * scale))), Image.LANCZOS)
            im.save(out, "WEBP", quality=quality, method=4)
            fin = os.path.getsize(f)
            fout = os.path.getsize(out)
            total_in += fin
            total_out += fout
        except Exception as e:
            errors.append((f, repr(e)))

    log(f"files={len(files)} ok={len(files)-len(errors)} err={len(errors)}")
    log(f"IN  = {total_in/1024/1024:.1f} MB")
    log(f"OUT = {total_out/1024/1024:.1f} MB")
    log(f"ratio = {total_out/total_in*100:.1f}%")
    for f, e in errors[:10]:
        log("ERR", f, e)

if __name__ == "__main__":
    try:
        main_run()
    except Exception:
        traceback.print_exc(file=LOG)
        log("FATAL", traceback.format_exc())
