"""Render submission/SUBMISSION.md to submission/SUBMISSION.html and, with headless Chrome, SUBMISSION.pdf.

The Markdown file is the single source; images are referenced relative to submission/. The PDF is printed from a
temporary copy whose screenshots are downscaled JPEGs, so it stays small enough to upload. Set PHL_CHROME to the
Chrome/Edge executable if it is not in a standard location.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from markdown_it import MarkdownIt
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SUB = ROOT / "submission"

CSS = """
@page { size: A4; margin: 14mm 14mm 16mm; }
:root { --ink:#1b2a2f; --muted:#56666c; --line:#d5e0e2; --brand:#0f8b8d; --warn-bg:#fff4dc; --warn:#7a5200; }
* { box-sizing: border-box; }
body { margin: 0 auto; max-width: 900px; padding: 24px 16px; background: #fff; color: var(--ink);
  font: 10.5pt/1.5 "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
h1 { font-size: 24pt; line-height: 1.15; margin: 6px 0 12px; }
h2 { font-size: 15pt; margin: 26px 0 8px; padding-bottom: 4px; border-bottom: 2px solid var(--brand); break-after: avoid; }
h3 { font-size: 11.5pt; margin: 16px 0 4px; color: var(--brand); break-after: avoid; }
p, li { orphans: 3; widows: 3; }
ul, ol { padding-left: 20px; margin: 4px 0 8px; }
code { font: 9pt Consolas, "Cascadia Mono", monospace; background: #f1f4f5; padding: 1px 4px; border-radius: 4px; }
pre { background: #f1f4f5; padding: 10px 12px; border-radius: 8px; overflow-x: auto; break-inside: avoid; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 12px; font-size: 9.5pt; break-inside: auto; }
th, td { border: 1px solid var(--line); padding: 5px 7px; text-align: left; vertical-align: top; }
th { background: #eef5f5; }
tr { break-inside: avoid; }
.cover { min-height: 250mm; display: flex; flex-direction: column; justify-content: center; break-after: page; }
.cover .kicker { color: var(--brand); font-weight: 700; letter-spacing: .04em; text-transform: uppercase; font-size: 10pt; }
.cover .lede { font-size: 12.5pt; color: var(--muted); max-width: 680px; }
.cover table { max-width: 560px; font-size: 10.5pt; }
.cover thead { display: none; }
.cover td:first-child { width: 140px; }
.note { background: var(--warn-bg); color: var(--warn); border-radius: 10px; padding: 12px 14px; font-size: 10pt; }
img.fig { width: 100%; display: block; margin: 8px 0 12px; border: 1px solid var(--line); border-radius: 8px; }
figure { margin: 10px 0 14px; break-inside: avoid; }
figure img.shot { width: 100%; display: block; border: 1px solid var(--line); border-radius: 8px; }
figcaption { font-size: 9pt; color: var(--muted); margin-top: 4px; }
.phones { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 10px 0 14px; break-inside: avoid; }
.phones figure { margin: 0; }
.phones img { width: 100%; border: 1px solid var(--line); border-radius: 10px; display: block; }
@media (max-width: 640px) { .phones { grid-template-columns: repeat(2, 1fr); } h1 { font-size: 20pt; } }
@media print { body { max-width: none; padding: 0; } a { color: inherit; text-decoration: none; } }
"""


def find_chrome() -> str | None:
    env = os.environ.get("PHL_CHROME")
    if env:
        return env
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome", "msedge"):
        if shutil.which(name):
            return shutil.which(name)
    return None


def main() -> int:
    md = MarkdownIt("commonmark", {"html": True}).enable("table")
    body = md.render((SUB / "SUBMISSION.md").read_text(encoding="utf-8"))
    html = (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Stage 3 Submission</title>"
        f"<style>{CSS}</style></head><body>\n{body}</body></html>\n"
    )
    out_html = SUB / "SUBMISSION.html"
    out_html.write_text(html, encoding="utf-8")
    print(f"wrote {out_html.relative_to(ROOT)}")

    chrome = find_chrome()
    if not chrome:
        print("Chrome/Edge not found: set PHL_CHROME to print the PDF. HTML is ready.")
        return 0
    out_pdf = SUB / "SUBMISSION.pdf"
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "screenshots").mkdir()
        for svg in SUB.glob("*.svg"):
            shutil.copy(svg, t / svg.name)
        for png in (SUB / "screenshots").glob("*.png"):
            im = Image.open(png).convert("RGB")
            im.thumbnail((1500, 1500))
            im.save(t / "screenshots" / (png.stem + ".jpg"), quality=82, optimize=True)
        print_html = t / "SUBMISSION.html"
        print_html.write_text(html.replace(".png\"", ".jpg\""), encoding="utf-8")
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        "--virtual-time-budget=5000", f"--print-to-pdf={out_pdf}", print_html.as_uri()],
                       check=True, capture_output=True)
    print(f"wrote {out_pdf.relative_to(ROOT)} ({out_pdf.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
