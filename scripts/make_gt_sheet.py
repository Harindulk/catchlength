"""Printable ground-truth sheet for the fish-market shoot: A4 portrait, 25 rows a page, filled in by hand with a pen.
Typed up afterwards as ground_truth.csv (batch,tag,species,fork_cm,notes), the file catchlength.audit grades against."""
import sys

from PIL import Image, ImageDraw, ImageFont

OUT = sys.argv[1] if len(sys.argv) > 1 else "print/catchlength_ground_truth_sheet.pdf"
PAGES, ROWS, DPI = 2, 25, 200
mm = lambda v: round(v * DPI / 25.4)
F = "/System/Library/Fonts/HelveticaNeue.ttc"
big, med, small = (ImageFont.truetype(F, mm(s)) for s in (6, 3.6, 2.8))
COLS = [("batch", 18), ("tag", 14), ("species", 46), ("fork length cm", 30), ("notes (curled, damaged, touching)", 72)]

pages = []
for p in range(PAGES):
    im = Image.new("L", (mm(210), mm(297)), 255)
    d = ImageDraw.Draw(im)
    x0, y = mm(12), mm(12)
    d.text((x0, y), "CatchLength ground truth", font=big, fill=0)
    d.text((mm(150), y + mm(1.5)), f"page {p + 1} of {PAGES}", font=med, fill=90)
    y += mm(10)
    d.text((x0, y), "Date ________   Market ______________   Measured by ______________", font=med, fill=0)
    y += mm(7)
    d.text((x0, y), "Fork length = snout tip to the inside of the tail fork, straight line, fish flat. Nearest 0.5 cm.",
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
    d.text((x0, y), "Manual timing: 10 fish measured and written took ____ min ____ s", font=med, fill=0)
    pages.append(im)
pages[0].save(OUT, save_all=True, append_images=pages[1:], resolution=DPI)
print(f"{OUT}: {PAGES} pages x {ROWS} rows")
