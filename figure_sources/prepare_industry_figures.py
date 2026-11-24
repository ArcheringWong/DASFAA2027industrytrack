"""Reflow the two Industry V2 diagrams for the LNCS column and export vector PDFs."""

from functools import lru_cache
from hashlib import sha256
from html import escape
from math import hypot
from pathlib import Path
import os
import re
import subprocess
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

from PIL import ImageFont
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas


OUT = Path(__file__).resolve().parent
SOURCE = OUT.parents[2] / "paper_industry_polish_v2"
SVG_TEXT = ".//{http://www.w3.org/2000/svg}text"
WIDTH = 460
FONT_DIR = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def labels_from(path):
    return ["".join(node.itertext()) for node in ElementTree.parse(path).findall(SVG_TEXT)]


@lru_cache(maxsize=None)
def font(size, bold):
    return ImageFont.truetype(str(FONT_DIR / ("arialbd.ttf" if bold else "arial.ttf")), round(10 * size))


def wrap(label, width, size, bold):
    lines = []
    current = ""
    for word in label.split():
        next_line = f"{current} {word}".strip()
        if current and font(size, bold).getlength(next_line) > 10 * width:
            lines.append(current)
            current = word
        else:
            current = next_line
    lines.append(current)
    require(all(font(size, bold).getlength(line) <= 10 * width for line in lines), f"Label does not fit: {label}")
    return lines


def rect(x, y, width, height, fill, stroke, dashed=False):
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    return (f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="5" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.1"{dash}/>')


def arrow(x0, y0, x1, y1):
    return (f'<path d="M{x0} {y0} L{x1} {y1}" fill="none" stroke="#40586a" '
            'stroke-width="1.15" marker-end="url(#arrow)"/>')


def text(label, x, y, width, size=10, bold=False, center=False, color="#172b3a", max_lines=2):
    lines = wrap(label, width, size, bold)
    require(len(lines) <= max_lines, f"Text exceeds reserved height: {label}")
    attributes = ('font-family="Arial, Helvetica, sans-serif" '
                  f'font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}" '
                  f'text-anchor="{"middle" if center else "start"}"')
    # The unchanged source label is attached to each structure for exact reflow verification.
    body = " ".join(f'<tspan x="{x}" y="{y + i * (size + 1.3):.2f}">{escape(line)}</tspan>'
                    for i, line in enumerate(lines))
    return f'<text {attributes} data-source-label="{escape(label, quote=True)}">{body}</text>'


def diagram(width, height, body):
    definition = ('<defs><marker id="arrow" markerWidth="6" markerHeight="5" refX="5.5" refY="2.5" '
                  'orient="auto"><path d="M0 0 L6 2.5 L0 5 Z" fill="#40586a"/></marker></defs>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">{definition}\n'
            f'<rect width="{width}" height="{height}" fill="#ffffff"/>\n'
            + "\n".join(body) + "\n</svg>\n")


def figure1(labels):
    require(len(labels) == 19, "Figure 1 source labels changed")
    body = []
    for lane, y, color, fill in ((0, 3, "#647d8e", "#f7f9fb"), (1, 76, "#0d6871", "#f1f8f9")):
        body.append(rect(2, y, 456, 67, fill, color, dashed=lane == 0))
        body.append(text(labels[lane * 9], 10, y + 13, 438, size=10.5, bold=True, max_lines=1))
        for node, x in enumerate((9, 123, 237, 351)):
            body.append(rect(x, y + 20, 100, 40, "#ffffff", color))
            idx = lane * 9 + 1 + 2 * node
            body.append(text(labels[idx], x + 50, y + 32, 96, size=9.8, bold=True, center=True, max_lines=1))
            body.append(text(labels[idx + 1], x + 50, y + 45, 95, size=9.5, center=True, color="#425868"))
            if node < 3:
                body.append(arrow(x + 101, y + 40, x + 112, y + 40))
    body.append(text(labels[-1], WIDTH / 2, 158, 436, size=9.5, center=True, color="#425868"))
    return diagram(WIDTH, 174, body)


def figure2(labels):
    require(len(labels) == 27, "Figure 2 source labels changed")
    body = []
    for panel, x in enumerate((3, 233)):
        first = 4 if panel == 0 else 15
        label_x, main_width = x + 11, 202
        body.append(rect(x, 3, 224, 301, "#fafbfd", "#a3b1ba"))
        body.append(text(labels[panel], x + 7, 17, 210, size=9.75, bold=True, max_lines=1))
        body.append(text(labels[panel + 2], x + 7, 32, 210, size=9.5, color="#516575"))
        for box, box_x in enumerate((x + 7, x + 118)):
            body.append(rect(box_x, 48, 99, 52, "#ffffff", "#647d8e"))
            body.append(text(labels[first + 2 * box], box_x + 5, 61, 89, size=9.6, bold=True))
            body.append(text(labels[first + 2 * box + 1], box_x + 5, 82, 89, size=9.5, max_lines=2))
        body.append(arrow(x + 107, 74, x + 117, 74))
        body.append(arrow(x + 167.5, 102, x + 167.5, 114))
        for offset, y, height, fill, stroke, dashed in (
            (4, 116, 49, "#fff3f1", "#a84333", False),
            (6, 180, 47, "#ffffff", "#a84333", True),
            (8, 242, 55, "#eaf0f4", "#526b7b", False),
        ):
            body.append(rect(x + 7, y, 210, height, fill, stroke, dashed))
            body.append(text(labels[first + offset], label_x, y + 12, main_width, size=9.6, bold=True, max_lines=1))
            body.append(text(labels[first + offset + 1], label_x, y + 25, main_width, size=9.5))
            if offset < 8:
                body.append(arrow(x + 112, y + height + 2, x + 112, y + height + 13))
            else:
                body.append(text(labels[first + offset + 2], label_x, y + 37, main_width, size=9.5,
                                 color="#516575"))
    body.append(text(labels[-1], WIDTH / 2, 320, 438, size=9.5, center=True, color="#516575"))
    return diagram(WIDTH, 330, body)


def run(args):
    return subprocess.run(args, check=True, capture_output=True, encoding="utf-8", errors="replace").stdout


def export_pdf(svg, pdf):
    """Export the rectangular, line-and-text diagram primitives as vector commands."""
    root = ElementTree.fromstring(svg)
    width, height = map(float, root.attrib["viewBox"].split()[2:])
    page = Canvas(str(pdf), pagesize=(.75 * width, .75 * height), invariant=1)
    page.scale(.75, .75)
    for node in root:
        tag, attrs = node.tag.rsplit("}", 1)[-1], node.attrib
        if tag == "defs":
            continue
        page.saveState()
        if tag == "rect":
            x, y, w, h = [float(attrs.get(key, 0)) for key in ("x", "y", "width", "height")]
            page.setFillColor(HexColor(attrs["fill"]))
            border = "stroke" in attrs
            if border:
                page.setStrokeColor(HexColor(attrs["stroke"]))
                page.setLineWidth(float(attrs["stroke-width"]))
            if "stroke-dasharray" in attrs:
                page.setDash(*map(float, attrs["stroke-dasharray"].split()))
            page.roundRect(x, height - y - h, w, h, float(attrs.get("rx", 0)), stroke=int(border), fill=1)
        elif tag == "path":
            x0, y0, x1, y1 = map(float, re.findall(r"-?\d+(?:\.\d+)?", attrs["d"]))
            y0, y1 = height - y0, height - y1
            color = HexColor(attrs["stroke"])
            page.setStrokeColor(color)
            page.setFillColor(color)
            page.setLineWidth(float(attrs["stroke-width"]))
            page.line(x0, y0, x1, y1)
            length = hypot(x1 - x0, y1 - y0)
            dx, dy = (x1 - x0) / length, (y1 - y0) / length
            head = page.beginPath()
            head.moveTo(x1, y1)
            head.lineTo(x1 - 6 * dx + 2.5 * dy, y1 - 6 * dy - 2.5 * dx)
            head.lineTo(x1 - 6 * dx - 2.5 * dy, y1 - 6 * dy + 2.5 * dx)
            head.close()
            page.drawPath(head, fill=1, stroke=0)
        elif tag == "text":
            face = "Arial-Bold" if attrs["font-weight"] == "700" else "Arial"
            size = float(attrs["font-size"])
            page.setFont(face, size)
            page.setFillColor(HexColor(attrs["fill"]))
            draw = page.drawCentredString if attrs["text-anchor"] == "middle" else page.drawString
            for child in node:
                x, y = float(child.attrib["x"]), height - float(child.attrib["y"])
                if "∅" not in child.text:
                    draw(x, y, child.text)
                    continue
                require(draw == page.drawString, "A centered fallback glyph needs a measured origin")
                before, _, after = child.text.partition("∅")
                line = page.beginText(x, y)
                line.setFont(face, size)
                line.textOut(before)
                line.setFont("Segoe-UI-Symbol", size)
                line.textOut("∅")
                line.setFont(face, size)
                line.textOut(after)
                page.drawText(line)
        else:
            raise ValueError(f"Unsupported diagram element: {tag}")
        page.restoreState()
    page.showPage()
    page.save()


def validate(svg, pdf, original_labels):
    actual = ElementTree.fromstring(svg).findall(SVG_TEXT)
    require(sorted(node.attrib["data-source-label"] for node in actual) == sorted(original_labels),
            f"Labels differ from the source in {pdf.name}")
    require(all(" ".join("".join(node.itertext()).split()) == " ".join(node.attrib["data-source-label"].split())
                for node in actual), f"Visible SVG label differs from the source in {pdf.name}")
    image_records = run(["pdfimages", "-list", str(pdf)]).splitlines()[2:]
    require(not any(row.strip() for row in image_records), f"Raster assets inside {pdf.name}")
    extracted = " ".join(run(["pdftotext", "-raw", "-enc", "UTF-8", str(pdf), "-"]).split())
    # Printed PDF must retain all source text, including the empty set symbol.
    require(all(" ".join(label.split()) in extracted for label in original_labels),
            f"PDF text differs from source: {[label for label in original_labels if ' '.join(label.split()) not in extracted]}")


def main():
    figures = (("figure1_reference_and_experiment", figure1), ("figure2_early_stop_paths", figure2))
    pdfmetrics.registerFont(TTFont("Arial", str(FONT_DIR / "arial.ttf")))
    pdfmetrics.registerFont(TTFont("Arial-Bold", str(FONT_DIR / "arialbd.ttf")))
    pdfmetrics.registerFont(TTFont("Segoe-UI-Symbol", str(FONT_DIR / "seguisym.ttf")))
    with TemporaryDirectory(prefix="dasfaa-industry-figures-") as temp:
        directory = Path(temp)
        for stem, reflow in figures:
            original = SOURCE / (stem + ".svg")
            original_labels = labels_from(original)
            svg = reflow(original_labels)
            pdf = directory / (stem + ".pdf")
            export_pdf(svg, pdf)
            validate(svg, pdf, original_labels)
            (OUT / pdf.name).write_bytes(pdf.read_bytes())
            (OUT / (stem + ".svg")).write_text(svg, encoding="utf-8", newline="\n")
            print(f"{stem}, vector PDF SHA-256 {sha256(pdf.read_bytes()).hexdigest()}, "
                  f"original SVG SHA-256 {sha256(original.read_bytes()).hexdigest()}", flush=True)


if __name__ == "__main__":
    main()
