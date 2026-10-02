"""Builds backend/assets/default_certificate.png from the customer's landscape PDF template."""
import pymupdf
from PIL import Image, ImageDraw

SRC = "/app/assets/diploma/Main File/Pdf/050521 Erlina -  Certificate - Lendscape.pdf"
OUT = "/app/backend/assets/default_certificate.png"
FONTS = "/app/backend/assets/fonts/"

doc = pymupdf.open(SRC)
p = doc[0]
for b in p.get_text("dict")["blocks"]:
    for line in b.get("lines", []):
        for s in line["spans"]:
            p.add_redact_annot(pymupdf.Rect(s["bbox"]))
p.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
# signature strokes, seal wording (vector) and placeholder company logo; keep images intact
for r in [(280, 425, 700, 500), (86, 410, 199, 513), (805, 22, 840, 54)]:
    p.add_redact_annot(pymupdf.Rect(*r))
p.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED)

p.insert_font(fontname="ral", fontfile=FONTS + "Raleway-Bold.ttf")
p.insert_font(fontname="slab", fontfile=FONTS + "RobotoSlab-Bold.ttf")
p.insert_font(fontname="rob", fontfile=FONTS + "Roboto-Regular.ttf")
white = (1, 1, 1)
ral = pymupdf.Font(fontfile=FONTS + "Raleway-Bold.ttf")
size = 46
while ral.text_length("CERTIFICADO", fontsize=size) > 235:
    size -= 1
p.insert_text((49, 150), "CERTIFICADO", fontname="ral", fontsize=size, color=white)
p.insert_text((49, 232), "DE APROBACIÓN", fontname="ral", fontsize=16, color=white)
p.insert_image(pymupdf.Rect(690, 14, 845, 155), filename="/app/backend/assets/logo.png", keep_proportion=True)
p.get_pixmap(dpi=200).save(OUT)
# paint over the stock seal so the QR can sit in that corner
im = Image.open(OUT).convert("RGB")
draw = ImageDraw.Draw(im)
draw.rectangle((217, 1117, 572, 1430), fill="white")
draw.rectangle((330, 1430, 572, 1458), fill="white")
im.save(OUT)
print("saved", OUT)
