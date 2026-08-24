# -*- coding: utf-8 -*-
"""
Extract Saint-Exupéry illustrations from the Russian PDF (v3, robust).

Two strategies, in order:
  A) Raster images present on the page -> use Document.extract_image(xref)
     to dump the ORIGINAL embedded bytes (no re-render, no crop -> never
     truncated). Saved as ill_p{pdfpage}_x{xref}.png.
  B) No raster but significant vector drawings -> render the whole page at
     ZOOM, paint text bboxes white, trim to content. Saved as
     ill_p{pdfpage}_v.png (vector fallback).

Filename convention is preserved so existing placement.json keeps working.
"""
import os, sys, json
import pymupdf as fitz
from PIL import Image, ImageDraw

PDF = r"D:\360极速浏览器X下载\Маленький принц (Сент-Экзюпери де Антуан).pdf"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "illustrations")
os.makedirs(OUT, exist_ok=True)

ZOOM = 2.0
DRAW_FRAC = 0.06
MIN_W, MIN_H = 60, 60

doc = fitz.open(PDF)
catalog = []

def trim(img, threshold=248, pad=10):
    g = img.convert("L")
    bbox = g.point(lambda v: 0 if v >= threshold else 255).getbbox()
    if not bbox:
        return img
    x0, y0, x1, y1 = bbox
    W, H = img.size
    x0 = max(0, x0 - pad); y0 = max(0, y0 - pad)
    x1 = min(W, x1 + pad); y1 = min(H, y1 + pad)
    return img.crop((x0, y0, x1, y1))

def render_full(page):
    pm = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), alpha=True)
    return Image.frombytes("RGBA", (pm.width, pm.height), pm.samples)

def paint_text_white(img, page):
    W, H = img.size
    mask = Image.new("L", (W, H), 0)
    drw = ImageDraw.Draw(mask)
    for block in page.get_text("blocks"):
        x0, y0, x1, y1, *_ = block
        drw.rectangle([x0*ZOOM, y0*ZOOM, x1*ZOOM, y1*ZOOM], fill=255)
    overlay = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    img.paste(overlay, (0, 0), mask)
    return img

processed_xref = set()

for pidx, page in enumerate(doc):
    pw, ph = page.rect.width, page.rect.height
    page_area = pw * ph
    text_n = len(page.get_text().strip())

    # --- Case A: native embedded raster images ---
    rasters = page.get_images(full=True)
    if rasters:
        for img in rasters:
            xref = img[0]
            if xref in processed_xref:
                continue
            processed_xref.add(xref)
            try:
                info = doc.extract_image(xref)
            except Exception as e:
                print(f"  p{pidx:03d} xref={xref} extract_image FAILED: {e}")
                continue
            ext = (info.get("ext") or "png").lower()
            raw = info.get("image")
            if not raw or len(raw) < 200:
                print(f"  p{pidx:03d} xref={xref} SKIP tiny/empty ({len(raw) if raw else 0} bytes)")
                continue
            fn = f"ill_p{pidx:03d}_x{xref}.png"
            outp = os.path.join(OUT, fn)
            if ext == "png":
                with open(outp, "wb") as f:
                    f.write(raw)
            else:
                # jpeg etc -> normalize to png
                try:
                    Image.open(outp if False else __import__("io").BytesIO(raw)).convert("RGBA").save(outp)
                except Exception:
                    with open(outp, "wb") as f:
                        f.write(raw)
            w, h = Image.open(outp).size
            if w < MIN_W or h < MIN_H:
                print(f"  p{pidx:03d} xref={xref} SKIP too small {w}x{h}")
                os.remove(outp)
                continue
            catalog.append({"pdf_page": pidx, "file": fn, "kind": "raster",
                            "w": w, "h": h, "text_n": text_n, "xref": xref})
            print(f"p{pidx:03d} xref={xref} -> {fn}  {w}x{h}  ({len(raw)} bytes)")
        continue

    # --- Case B: vector drawing dominant -> whole-page render ---
    drawings = [d for d in page.get_drawings() if d.get("rect")]
    if not drawings:
        continue
    db = None
    for d in drawings:
        r = fitz.Rect(d["rect"])
        db = r if db is None else db | r
    if not db:
        continue
    frac = abs(db.get_area()) / page_area
    if frac < DRAW_FRAC:
        continue
    img = render_full(page)
    if text_n > 30:
        img = paint_text_white(img, page)
    pad = 0.03
    cr = db + (-db.width*pad, -db.height*pad, db.width*pad, db.height*pad)
    crop = img.crop((int(cr.x0*ZOOM), int(cr.y0*ZOOM), int(cr.x1*ZOOM), int(cr.y1*ZOOM)))
    if crop.size[0] < MIN_W or crop.size[1] < MIN_H:
        continue
    crop = trim(crop)
    fn = f"ill_p{pidx:03d}_v.png"
    crop.convert("RGBA").save(os.path.join(OUT, fn))
    catalog.append({"pdf_page": pidx, "file": fn, "kind": "vector",
                    "w": crop.size[0], "h": crop.size[1], "text_n": text_n})
    print(f"p{pidx:03d} vector  -> {fn}  {crop.size[0]}x{crop.size[1]}  frac={frac:.3f}")

with open(os.path.join(OUT, "_catalog.json"), "w", encoding="utf-8") as f:
    json.dump(catalog, f, ensure_ascii=False, indent=2)
print(f"\nTotal: {len(catalog)} illustrations -> {OUT}")
