#!/usr/bin/env python3
"""Import trip photos and rebuild a gallery page's HTML.

Usage:
  python tools/sync_gallery.py <page> --input <folder>
      Convert every HEIC/JPG/PNG in <folder> to web-ready JPEGs, number them
      gallery-N.jpg (continuing after whatever is already in the gallery
      folder), drop them into staticfiles/img/gallery/<page>/, and rewrite
      the <gallery-item> blocks in <page>.html to match.

  python tools/sync_gallery.py <page>
      No new photos -- just regenerate <page>.html from whatever files are
      currently sitting in staticfiles/img/gallery/<page>/. Useful if the
      HTML and the folder ever drift apart (e.g. photos added/removed by
      hand), or to re-run after fixing something.

<page> must match both <page>.html and the folder name under
staticfiles/img/gallery/.
"""
import argparse
import re
import sys
from pathlib import Path

from PIL import Image, ImageOps
import pillow_heif

pillow_heif.register_heif_opener()

ROOT = Path(__file__).resolve().parent.parent
MAX_WIDTH = 2400
JPEG_QUALITY = 85
SOURCE_EXTS = {".heic", ".heif", ".jpg", ".jpeg", ".png"}
EXIF_DATETIME_ORIGINAL = 36867
EXIF_DATETIME = 306

ITEM_TEMPLATE = """          <div class="col-xl-3 col-lg-4 col-md-6">
            <div class="gallery-item h-100">
              <img src="/staticfiles/img/gallery/{name}/{filename}" class="img-fluid" alt="">
              <div class="gallery-links d-flex align-items-center justify-content-center">
                <a href="/staticfiles/img/gallery/{name}/{filename}" class="glightbox preview-link"><i class="bi bi-arrows-angle-expand"></i></a>
              </div>
            </div>
          </div><!-- End Gallery Item -->"""

ROW_RE = re.compile(
    r'(<div class="row gy-4 justify-content-center">\n)(.*?)(\n\s*</div>\s*\n\s*</div>\s*\n\s*</section><!-- End Gallery Section -->)',
    re.DOTALL,
)


def natural_key(p: Path) -> int:
    m = re.search(r"(\d+)", p.stem)
    return int(m.group(1)) if m else 0


def capture_time(p: Path):
    try:
        exif = Image.open(p).getexif()
        return exif.get(EXIF_DATETIME_ORIGINAL) or exif.get(EXIF_DATETIME) or ""
    except Exception:
        return ""


def import_photos(input_dir: Path, dest_dir: Path) -> int:
    dest_dir.mkdir(parents=True, exist_ok=True)
    existing = [natural_key(p) for p in dest_dir.glob("gallery-*.jpg")]
    next_n = max(existing, default=0) + 1

    files = [p for p in input_dir.iterdir() if p.suffix.lower() in SOURCE_EXTS]
    files.sort(key=lambda p: (capture_time(p) or "9999", p.stat().st_mtime, p.name))

    imported = 0
    for src in files:
        img = Image.open(src)
        img = ImageOps.exif_transpose(img)
        if img.mode != "RGB":
            img = img.convert("RGB")
        if img.width > MAX_WIDTH:
            ratio = MAX_WIDTH / img.width
            img = img.resize((MAX_WIDTH, round(img.height * ratio)), Image.LANCZOS)

        dest_name = f"gallery-{next_n}.jpg"
        img.save(dest_dir / dest_name, "JPEG", quality=JPEG_QUALITY, optimize=True)
        print(f"  {src.name} -> {dest_name}")
        next_n += 1
        imported += 1

    return imported


def rebuild_html(page: str, dest_dir: Path) -> None:
    html_path = ROOT / f"{page}.html"
    if not html_path.exists():
        sys.exit(f"error: {html_path} not found")

    files = sorted(dest_dir.glob("gallery-*.jpg"), key=natural_key)
    if not files:
        print(f"warning: no gallery-*.jpg files found in {dest_dir}")

    items_html = "\n".join(
        ITEM_TEMPLATE.format(name=page, filename=f.name) for f in files
    )

    text = html_path.read_text(encoding="utf-8")
    new_text, count = ROW_RE.subn(
        lambda m: m.group(1) + items_html + m.group(3), text, count=1
    )
    if count == 0:
        sys.exit(f"error: could not find gallery row markup in {html_path}")

    html_path.write_text(new_text, encoding="utf-8")
    print(f"updated {html_path.name} with {len(files)} photo(s)")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("page", help="page/gallery name, e.g. colorado")
    parser.add_argument("--input", help="folder of new photos to import (HEIC/JPG/PNG)")
    args = parser.parse_args()

    dest_dir = ROOT / "staticfiles" / "img" / "gallery" / args.page

    if args.input:
        input_dir = Path(args.input)
        if not input_dir.is_dir():
            sys.exit(f"error: {input_dir} is not a folder")
        n = import_photos(input_dir, dest_dir)
        print(f"imported {n} photo(s) into {dest_dir}")

    rebuild_html(args.page, dest_dir)


if __name__ == "__main__":
    main()
