"""Printable ground-truth sheet for the shoot: A4 portrait, 25 rows a page, filled in by hand with a pen.
Typed up afterwards as ground_truth.csv (batch,tag,species,fork_cm,fork_cm_2,total_cm,total_cm_2,notes): catchlength.audit
grades fork length, scripts/tl_compare.py total length (the measure NARA reports)."""
import sys

from PIL import Image, ImageDraw, ImageFont

OUT = sys.argv[1] if len(sys.argv) > 1 else "print/catchlength_ground_truth_sheet.pdf"
PAGES, ROWS, DPI = 2, 25, 200
mm = lambda v: round(v * DPI / 25.4)
F = "/System/Library/Fonts/HelveticaNeue.ttc"
big, med, small = (ImageFont.truetype(F, mm(s)) for s in (6, 3.6, 2.8))
COLS = [("batch", 13), ("tag", 11), ("species", 30), ("fork length cm", 24), ("2nd fork", 20), ("TOTAL length cm", 26),
        ("2nd total", 20), ("notes (curled, damaged)", 42)]

pages = []
for p in range(PAGES):
    im = Image.new("L", (mm(210), mm(297)), 255)
    d = ImageDraw.Draw(im)
    x0, y = mm(12), mm(12)
    d.text((x0, y), "CatchLength ground truth", font=big, fill=0)
    d.text((mm(150), y + mm(1.5)), f"page {p + 1} of {PAGES}", font=med, fill=90)
    y += mm(10)
    d.text((x0, y), "Date ________   Place ______________   Measured by ______________", font=med, fill=0)
    y += mm(7)
    d.text((x0, y), "Snout against the stop. Fork: inside of the tail fork. TOTAL: tip of the tail, lobes closed. Nearest 0.5 cm.",
           font=small, fill=60)
    y += mm(5)
    d.text((x0, y), "Tags run 1, 2, 3 ... across the whole day, never restarting at 1. 2nd fork / 2nd total: lift, re-lay, re-measure.",
           font=small, fill=60)
    y += mm(5)
    d.text((x0, y), "Per batch, on the back: clip file names, time, number of fish, which tiles were in view.", font=small, fill=60)
    y += mm(8)
    rh = mm(8.6)
    x = x0
    for name, w in COLS:
        d.rectangle([x, y, x + mm(w), y + rh], outline=0, width=2, fill=230)
        d.text((x + mm(1.5), y + mm(2.6)), name, font=small, fill=0)
        x += mm(w)
    for r in range(ROWS):
        y += rh
        x = x0
        for _, w in COLS:
            d.rectangle([x, y, x + mm(w), y + rh], outline=0, width=1)
            x += mm(w)
    y += rh + mm(5)
    d.text((x0, y), "Species: skipjack (balaya) · kawakawa (attawalla) · Indian mackerel (kumbalawa) · frigate tuna (alagoduwa) · "
           "bullet tuna", font=small, fill=60)
    y += mm(5)
    d.text((x0, y), "Stopwatch, 10 fish by hand (measure + write): ____ min ____ s", font=med, fill=0)
    y += mm(6)
    d.text((x0, y), "Stopwatch, the same 10 for the agent (lay out + tag + film): ____ min ____ s", font=med, fill=0)
    pages.append(im)
pages[0].save(OUT, save_all=True, append_images=pages[1:], resolution=DPI)
print(f"{OUT}: {PAGES} pages x {ROWS} rows")
