import io
import base64
from pathlib import Path

import pymupdf
import qrcode

ASSETS = Path(__file__).parent / "assets"
FONTS = ASSETS / "fonts"
DEFAULT_TEMPLATE = ASSETS / "default_certificate.png"

DEFAULT_LAYOUT = {
    "align": "left", "text_x": 37, "text_w": 57, "color": "#1f2933",
    "name_y": 32, "course_y": 45, "sign_y": 60.5, "sign_x": 36, "sign_w": 42,
    "qr_x": 10.5, "qr_y": 66, "qr_size": 12.5,
}
SIG_H = 8
_FONT_FILES = {"name": "LibreBaskerville-Italic.ttf", "bold": "Raleway-Bold.ttf", "reg": "Roboto-Regular.ttf",
               "lora": "Lora-Regular.ttf", "lorai": "Lora-Italic.ttf", "mono": "RobotoMono-Bold.ttf"}
_FONTS = {k: pymupdf.Font(fontfile=str(FONTS / f)) for k, f in _FONT_FILES.items()}


def template_to_png(data: bytes, content_type: str) -> bytes:
    if content_type == "application/pdf" or data[:4] == b"%PDF":
        doc = pymupdf.open(stream=data, filetype="pdf")
        return doc[0].get_pixmap(dpi=200).tobytes("png")
    return data


def _rgb(hex_color: str):
    h = (hex_color or "#1f2933").lstrip("#")
    try:
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return (0.12, 0.16, 0.2)


def _sig_bytes(data_url: str):
    if data_url and data_url.startswith("data:image/png;base64,"):
        return base64.b64decode(data_url.split(",", 1)[1])
    return None


def _qr_png(url: str) -> bytes:
    img = qrcode.make(url, box_size=10, border=1)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class _Writer:
    def __init__(self, page, layout):
        self.p, self.L = page, layout
        self.W, self.H = page.rect.width, page.rect.height
        for k, f in _FONT_FILES.items():
            page.insert_font(fontname=k, fontfile=str(FONTS / f))

    def x(self, pct):
        return self.W * pct / 100

    def y(self, pct):
        return self.H * pct / 100

    def line(self, text, font, size, y_pct, color, x_pct=None, w_pct=None, align=None, min_size=6):
        x0, w = self.x(x_pct if x_pct is not None else self.L["text_x"]), self.x(w_pct if w_pct is not None else self.L["text_w"])
        while size > min_size and _FONTS[font].text_length(text, fontsize=size) > w:
            size -= 0.5
        tw = _FONTS[font].text_length(text, fontsize=size)
        align = align or self.L["align"]
        x = x0 + (w - tw) / 2 if align == "center" else x0
        self.p.insert_text((x, self.y(y_pct) + size), text, fontname=font, fontsize=size, color=color)
        return size

    def wrapped(self, text, font, size, y_pct, color, max_lines=2):
        w = self.x(self.L["text_w"])
        words, lines, cur = text.split(), [], ""
        for wd in words:
            test = f"{cur} {wd}".strip()
            if _FONTS[font].text_length(test, fontsize=size) <= w or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = wd
        lines.append(cur)
        if len(lines) > max_lines:
            return self.wrapped(text, font, size - 1, y_pct, color, max_lines)
        step = size * 1.25 / self.H * 100
        for i, ln in enumerate(lines):
            self.line(ln, font, size, y_pct + i * step, color)
        return y_pct + len(lines) * step


def render_certificate(template_png: bytes, data: dict, layout: dict, signatures: list) -> bytes:
    L = {**DEFAULT_LAYOUT, **{k: v for k, v in (layout or {}).items() if v not in (None, "")}}
    pix = pymupdf.Pixmap(template_png)
    W = 858.9
    H = W * pix.height / pix.width
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)
    page.insert_image(page.rect, stream=template_png)
    w = _Writer(page, L)
    ink, soft = _rgb(L["color"]), (0.38, 0.41, 0.45)

    w.line("SE OTORGA EL PRESENTE CERTIFICADO A", "reg", 9.5, L["name_y"] - 4.5, soft)
    w.line(data["student_name"], "name", 38, L["name_y"], ink)
    w.line("POR HABER APROBADO SATISFACTORIAMENTE EL CURSO", "reg", 9.5, L["course_y"], soft)
    end = w.wrapped(data["course_title"], "bold", 18, L["course_y"] + 3.6, ink)
    details = [d for d in (f"RUT {data['rut']}" if data.get("rut") else "",
                           f"{data['hours']} horas cronológicas" if data.get("hours") else "",
                           f"Nota final {data['nota']}" if data.get("nota") else "", data.get("date_text", "")) if d]
    w.line("  ·  ".join(details), "reg", 10, end + 1.2, soft)

    col_w = L["sign_w"] / max(1, len(signatures))
    for i, (img, name, role) in enumerate(signatures):
        cx = L["sign_x"] + col_w * i
        pad = col_w * 0.08
        img_bytes = _sig_bytes(img)
        if img_bytes:
            page.insert_image(pymupdf.Rect(w.x(cx + pad), w.y(L["sign_y"]), w.x(cx + col_w - pad), w.y(L["sign_y"] + SIG_H)),
                              stream=img_bytes, keep_proportion=True)
        ly = w.y(L["sign_y"] + SIG_H + 0.7)
        page.draw_line((w.x(cx + pad), ly), (w.x(cx + col_w - pad), ly), color=(0.45, 0.46, 0.48), width=0.6)
        w.line(name or " ", "lora", 9.5, L["sign_y"] + SIG_H + 1.3, ink, cx + pad, col_w - 2 * pad, "center")
        w.line(role, "lorai", 8, L["sign_y"] + SIG_H + 3.9, soft, cx + pad, col_w - 2 * pad, "center")

    size = w.x(L["qr_size"])
    qx, qy = w.x(L["qr_x"]), w.y(L["qr_y"])
    page.insert_image(pymupdf.Rect(qx, qy, qx + size, qy + size), stream=_qr_png(data["verify_url"]))
    qx_pct, q_end = L["qr_x"], L["qr_y"] + size / H * 100
    w.line("CÓDIGO DE APROBACIÓN", "reg", 5.5, q_end + 0.8, soft, qx_pct - 2, L["qr_size"] + 4, "center")
    w.line(data["code"], "mono", 8, q_end + 2.6, ink, qx_pct - 3, L["qr_size"] + 6, "center")
    w.line("Escanea para verificar", "reg", 5.5, q_end + 5, soft, qx_pct - 2, L["qr_size"] + 4, "center")
    return doc.tobytes(garbage=3, deflate=True)
