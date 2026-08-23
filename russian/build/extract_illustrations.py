# -*- coding: utf-8 -*-
"""
Extract Saint-Exupéry illustrations from the Russian PDF (v2, cleaner).

For each page:
  - If the page has at least one raster image (get_images), crop the union
    of image_rects and save (no text mask needed).
  - Else, if the page has substantial vector drawings (>= DRAW_FRAC of
    page area), and the text is short (page is essentially an illustration
    page with maybe a chapter title), render the page, paint all text
    bboxes white to get a clean illustration, trim, save.
  - Else, skip (pure text page).
"""
import os, sys, json
import pymupdf as fitz
from PIL import Image, ImageDraw

PDF = r"D:\360极速浏览器X下载\Маленький принц (Сент-Экзюпери де Антуан).pdf"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "illustrations")
os.makedirs(OUT, exist_ok=True)

ZOOM = 2.0
DRAW_FRAC = 0.06        # vector drawings must cover this fraction to count
COV_FRAC  = 0.005       # min non-white fraction to keep crop
MIN_SIZE  = 100         # min pixel side to keep crop

doc = fitz.open(PDF)
catalog = []

def union(rects):
    if not rects: return None
    return fitz.Rect(min(r.x0 for r in rects), min(r.y0 for r in rects),
                     max(r.x1 for r in rects), max(r.y1 for r in rects))

def nonwhite_frac(img):
    g = img.convert("L")
    px = list(g.getdata())
    return sum(1 for v in px if v < 250) / max(1, len(px))

def trim(img, threshold=248, pad=8):
    g = img.convert("L")
    bbox = g.point(lambda v: 0 if v >= threshold else 255).getbbox()
    if not bbox: return img
    x0, y0, x1, y1 = bbox
    W, H = img.size
    x0 = max(0, x0 - pad); y0 = max(0, y0 - pad)
    x1 = min(W, x1 + pad); y1 = min(H, y1 + pad)
    return img.crop((x0, y0, x1, y1))

def render_full(page):
    pm = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), alpha=True)
    return Image.frombytes("RGBA", (pm.width, pm.height), pm.samples)

def paint_text_white(img, page):
    """Overlay white where text bboxes are."""
    W, H = img.size
    mask = Image.new("L", (W, H), 0)
    drw = ImageDraw.Draw(mask)
    for block in page.get_text("blocks"):
        x0, y0, x1, y1, *_ = block
        drw.rectangle([x0*ZOOM, y0*ZOOM, x1*ZOOM, y1*ZOOM], fill=255)
    overlay = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    img.paste(overlay, (0, 0), mask)
    return img

for pidx, page in enumerate(doc):
    pw, ph = page.rect.width, page.rect.height
    page_area = pw * ph
    text_n = len(page.get_text().strip())

    # --- Case A: page has raster image(s) ---
    rasters = []
    for img in page.get_images(full=True):
        xref = img[0]
        try:
            for r in page.get_image_rects(xref):
                rasters.append((xref, r))
        except: pass
    if rasters:
        # group by xref: a single raster may appear multiple times; dedupe by xref+bbox
        # just iterate and save each unique bbox
        seen = set()
        for xref, r in rasters:
            key = (xref, round(r.x0,1), round(r.y0,1), round(r.x1,1), round(r.y1,1))
            if key in seen: continue
            seen.add(key)
            # render crop
            pad = 0.04
            cr = r + (-r.width*pad, -r.height*pad, r.width*pad, r.height*pad)
            full = render_full(page)
            crop = full.crop((int(cr.x0*ZOOM), int(cr.y0*ZOOM), int(cr.x1*ZOOM), int(cr.y1*ZOOM)))
            if crop.size[0] < MIN_SIZE or crop.size[1] < MIN_SIZE:
                continue
            if nonwhite_frac(crop) < COV_FRAC:
                continue
            crop = trim(crop)
            fn = f"ill_p{pidx:03d}_x{xref}.png"
            crop.convert("RGBA").save(os.path.join(OUT, fn))
            catalog.append({
                "pdf_page": pidx, "file": fn, "kind": "raster",
                "w": crop.size[0], "h": crop.size[1],
                "text_n": text_n, "xref": xref,
            })
            print(f"p{pidx:03d} xref={xref} -> {fn}  {crop.size[0]}x{crop.size[1]}  text_n={text_n}")
        # do not also try vector mode for this page
        continue

    # --- Case B: page is vector-drawing dominant ---
    drawings = [d for d in page.get_drawings() if d.get("rect")]
    if not drawings:
        continue
    db = union([fitz.Rect(d["rect"]) for d in drawings])
    if not db: continue
    frac = abs(db.get_area()) / page_area
    if frac < DRAW_FRAC:
        continue
    # Render full page + paint text white
    img = render_full(page)
    if text_n > 30:
        img = paint_text_white(img, page)
    # Crop to drawings bbox with small pad
    pad = 0.03
    cr = db + (-db.width*pad, -db.height*pad, db.width*pad, db.height*pad)
    crop = img.crop((int(cr.x0*ZOOM), int(cr.y0*ZOOM), int(cr.x1*ZOOM), int(cr.y1*ZOOM)))
    if crop.size[0] < MIN_SIZE or crop.size[1] < MIN_SIZE:
        continue
    if nonwhite_frac(crop) < COV_FRAC:
        continue
    crop = trim(crop)
    fn = f"ill_p{pidx:03d}_v.png"
    crop.convert("RGBA").save(os.path.join(OUT, fn))
    catalog.append({
        "pdf_page": pidx, "file": fn, "kind": "vector",
        "w": crop.size[0], "h": crop.size[1],
        "text_n": text_n, "draw_frac": round(frac, 4),
    })
    print(f"p{pidx:03d} vector  -> {fn}  {crop.size[0]}x{crop.size[1]}  frac={frac:.3f}  text_n={text_n}")

with open(os.path.join(OUT, "_catalog.json"), "w", encoding="utf-8") as f:
    json.dump(catalog, f, ensure_ascii=False, indent=2)
print(f"\nTotal: {len(catalog)} illustrations -> {OUT}")
