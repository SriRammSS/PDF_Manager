"""PDF edit service - apply visual editor operations with pikepdf."""

import math
import re
from pathlib import Path

import pikepdf


def hex_to_rgb_float(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return (
        int(h[0:2], 16) / 255,
        int(h[2:4], 16) / 255,
        int(h[4:6], 16) / 255,
    )


def apply_operations(source_path: str, ops: list, dest_path: str) -> int:
    with pikepdf.open(source_path) as pdf:
        annot_ops = [op for op in ops if op["type"] != "page"]
        page_ops = [op for op in ops if op["type"] == "page"]

        for op in annot_ops:
            page_idx = op["page"]
            if page_idx >= len(pdf.pages):
                raise ValueError(f"Page {page_idx} out of range")
            page = pdf.pages[page_idx]
            _ensure_fonts(pdf, page)

            t = op["type"]
            if t == "text":
                _apply_text(pdf, page, op)
            elif t == "highlight":
                _apply_highlight(pdf, page, op)
            elif t == "erase":
                _apply_erase(pdf, page, op)
            elif t == "shape":
                _apply_shape(pdf, page, op)
            elif t == "draw":
                _apply_draw(pdf, page, op)

        # Apply page ops: reorder first, then rotate, then delete
        for op in sorted(
            page_ops,
            key=lambda o: ["reorder", "rotate", "delete"].index(o["action"]),
        ):
            if op["action"] == "reorder" and op.get("new_order"):
                new_pages = [pdf.pages[i] for i in op["new_order"]]
                while len(pdf.pages):
                    del pdf.pages[0]
                for p in new_pages:
                    pdf.pages.append(p)
            elif op["action"] == "rotate":
                page = pdf.pages[op["page"]]
                cur = int(page.get("/Rotate", 0))
                page["/Rotate"] = (cur + op.get("rotate_degrees", 90)) % 360
            elif op["action"] == "delete":
                if len(pdf.pages) > 1:
                    del pdf.pages[op["page"]]

        tmp = dest_path + ".tmp"
        pdf.save(tmp)

    Path(tmp).rename(dest_path)
    with pikepdf.open(dest_path) as saved:
        return len(saved.pages)


def _ensure_fonts(pdf: pikepdf.Pdf, page: pikepdf.Object) -> None:
    if "/Resources" not in page:
        page["/Resources"] = pikepdf.Dictionary()
    res = page["/Resources"]
    if "/Font" not in res:
        res["/Font"] = pikepdf.Dictionary()
    fonts = {
        "Helvetica": "Helvetica",
        "HelveticaBold": "Helvetica-Bold",
        "HelveticaOblique": "Helvetica-Oblique",
        "HelveticaBoldOblique": "Helvetica-BoldOblique",
        "TimesRoman": "Times-Roman",
        "TimesBold": "Times-Bold",
        "TimesItalic": "Times-Italic",
        "TimesBoldItalic": "Times-BoldItalic",
        "Courier": "Courier",
        "CourierBold": "Courier-Bold",
    }
    for key, base in fonts.items():
        pkey = f"/{key}"
        if pkey not in res["/Font"]:
            res["/Font"][pkey] = pikepdf.Dictionary(
                Type=pikepdf.Name.Font,
                Subtype=pikepdf.Name.Type1,
                BaseFont=pikepdf.Name("/" + base),
            )


def _append_stream(pdf: pikepdf.Pdf, page: pikepdf.Object, content: bytes) -> None:
    s = pikepdf.Stream(pdf, content)
    if "/Contents" not in page:
        page["/Contents"] = pdf.make_indirect(s)
    else:
        ex = page["/Contents"]
        if isinstance(ex, pikepdf.Array):
            ex.append(pdf.make_indirect(s))
        else:
            page["/Contents"] = pikepdf.Array([ex, pdf.make_indirect(s)])


def _apply_text(pdf: pikepdf.Pdf, page: pikepdf.Object, op: dict) -> None:
    r, g, b = hex_to_rgb_float(op.get("color_hex", "#000000"))
    fs = op.get("font_size", 12)
    bold = op.get("bold", False)
    italic = op.get("italic", False)
    fam = op.get("font_family", "Helvetica")

    if fam == "Helvetica":
        fname = (
            "HelveticaBoldOblique"
            if bold and italic
            else "HelveticaBold"
            if bold
            else "HelveticaOblique"
            if italic
            else "Helvetica"
        )
    elif fam == "Times-Roman":
        fname = (
            "TimesBoldItalic"
            if bold and italic
            else "TimesBold"
            if bold
            else "TimesItalic"
            if italic
            else "TimesRoman"
        )
    else:
        fname = "CourierBold" if bold else "Courier"

    txt = op["text"].replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    x, y = op["x"], op["y"]
    rot = op.get("rotation", 0)

    if rot != 0:
        rad = math.radians(rot)
        c, s = math.cos(rad), math.sin(rad)
        pos = f"{c:.4f} {s:.4f} {-s:.4f} {c:.4f} {x:.2f} {y:.2f} Tm"
    else:
        pos = f"{x:.2f} {y:.2f} Td"

    content = (
        f"q\n{r:.4f} {g:.4f} {b:.4f} rg\nBT\n/{fname} {fs:.1f} Tf\n{pos}\n({txt}) Tj\nET\nQ\n"
    ).encode()
    _append_stream(pdf, page, content)


def _apply_highlight(pdf: pikepdf.Pdf, page: pikepdf.Object, op: dict) -> None:
    r, g, b = hex_to_rgb_float(op.get("color_hex", "#FFFF00"))
    opacity = op.get("opacity", 0.4)
    x, y, w, h = op["x"], op["y"], op["width"], op["height"]
    res = page["/Resources"]
    if "/ExtGState" not in res:
        res["/ExtGState"] = pikepdf.Dictionary()
    res["/ExtGState"]["/HLState"] = pikepdf.Dictionary(
        Type=pikepdf.Name.ExtGState, ca=opacity, CA=opacity
    )
    content = (
        f"q\n/HLState gs\n{r:.4f} {g:.4f} {b:.4f} rg\n{x:.2f} {y:.2f} {w:.2f} {h:.2f} re\nf\nQ\n"
    ).encode()
    _append_stream(pdf, page, content)


def _apply_erase(pdf: pikepdf.Pdf, page: pikepdf.Object, op: dict) -> None:
    r, g, b = hex_to_rgb_float(op.get("fill_color", "#FFFFFF"))
    x, y, w, h = op["x"], op["y"], op["width"], op["height"]
    content = (
        f"q\n{r:g} {g:g} {b:g} rg\n{x:.2f} {y:.2f} {w:.2f} {h:.2f} re\nf\nQ\n"
    ).encode()
    _append_stream(pdf, page, content)


def _apply_shape(pdf: pikepdf.Pdf, page: pikepdf.Object, op: dict) -> None:
    sr, sg, sb = hex_to_rgb_float(op.get("stroke_color", "#000000"))
    sw = op.get("stroke_width", 1.5)
    x, y, w, h = op["x"], op["y"], op["width"], op["height"]
    fc = op.get("fill_color")
    if op.get("shape_type") == "line":
        content = (
            f"q\n{sr:.4f} {sg:.4f} {sb:.4f} RG\n{sw:.2f} w\n{x:.2f} {y:.2f} m\n{x+w:.2f} {y+h:.2f} l\nS\nQ\n"
        ).encode()
    else:
        if fc:
            fr, fg, fb = hex_to_rgb_float(fc)
            body = f"{fr:.4f} {fg:.4f} {fb:.4f} rg\n{x:.2f} {y:.2f} {w:.2f} {h:.2f} re\nB\n"
        else:
            body = f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re\nS\n"
        content = (f"q\n{sr:.4f} {sg:.4f} {sb:.4f} RG\n{sw:.2f} w\n{body}Q\n").encode()
    _append_stream(pdf, page, content)


def _apply_draw(pdf: pikepdf.Pdf, page: pikepdf.Object, op: dict) -> None:
    r, g, b = hex_to_rgb_float(op.get("color_hex", "#000000"))
    sw = op.get("stroke_width", 2.0)
    pdf_path = _svg_to_pdf_path(op.get("path", ""))
    if not pdf_path:
        return
    content = (
        f"q\n{r:.4f} {g:.4f} {b:.4f} RG\n{sw:.2f} w\n1 J 1 j\n{pdf_path}\nS\nQ\n"
    ).encode()
    _append_stream(pdf, page, content)


def _svg_to_pdf_path(path_str: str) -> str:
    tokens = re.findall(r"[MLCQZmlcqz]|[-+]?[0-9]*\.?[0-9]+", path_str)
    result: list[str] = []
    i, cmd = 0, None
    while i < len(tokens):
        t = tokens[i]
        if t.isalpha():
            cmd = t
            i += 1
            continue
        try:
            if cmd in ("M", "m"):
                x, y = float(tokens[i]), float(tokens[i + 1])
                i += 2
                result.append(f"{x:.2f} {y:.2f} m")
            elif cmd in ("L", "l"):
                x, y = float(tokens[i]), float(tokens[i + 1])
                i += 2
                result.append(f"{x:.2f} {y:.2f} l")
            elif cmd in ("C", "c"):
                vals = [float(tokens[i + j]) for j in range(6)]
                i += 6
                result.append(
                    f"{vals[0]:.2f} {vals[1]:.2f} {vals[2]:.2f} {vals[3]:.2f} {vals[4]:.2f} {vals[5]:.2f} c"
                )
            elif cmd in ("Q", "q"):
                vals = [float(tokens[i + j]) for j in range(4)]
                i += 4
                result.append(
                    f"{vals[0]:.2f} {vals[1]:.2f} {vals[2]:.2f} {vals[3]:.2f} v"
                )
            elif cmd in ("Z", "z"):
                result.append("h")
                i += 1
            else:
                i += 1
        except (IndexError, ValueError):
            break
    return "\n".join(result)
