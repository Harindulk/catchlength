"""Write the printable A4 tile set as one PDF, one tile per landscape page, at exact scale (print at 100%)."""
import sys

from PIL import Image

from catchlength.mat import MATS, render, tile

N = int(sys.argv[1]) if len(sys.argv) > 1 else 4
OUT = sys.argv[2] if len(sys.argv) > 2 else "print/catchlength_A4_tiles.pdf"
DPI = 300
pages = [Image.fromarray(render(tile(MATS["A4"], k), px_per_mm=DPI / 25.4)) for k in range(N)]
pages[0].save(OUT, save_all=True, append_images=pages[1:], resolution=DPI)
print(f"{OUT}: {N} tiles, {pages[0].width}x{pages[0].height}px at {DPI} dpi = 297x210 mm")
