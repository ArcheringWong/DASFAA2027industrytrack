"""Rebuild both diagrams from local inspected layout code and SVG labels."""

import argparse
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def module(name, file):
    spec = spec_from_file_location(name, file)
    result = module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    source = ROOT / "figure_sources"
    draw = module("drawing_primitives", source / "prepare_industry_figures.py")
    technical = module("technical_layout", source / "prepare_early_stop_figure.py")
    for name, file in (("Arial", "arial.ttf"), ("Arial-Bold", "arialbd.ttf"),
                       ("Segoe-UI-Symbol", "seguisym.ttf")):
        draw.pdfmetrics.registerFont(draw.TTFont(name, str(draw.FONT_DIR / file)))
    reference = source / "figure1_reference_and_experiment.svg"
    labels = draw.labels_from(reference)
    svg, tech_labels = technical.layout(draw)
    figures = (
        ("figure1_reference_and_experiment", draw.figure1(labels), labels),
        ("figure2_early_stop_paths", svg, tech_labels),
    )
    records = []
    for stem, content, expected_labels in figures:
        expected_svg = (source / (stem + ".svg")).read_text(encoding="utf8")
        if content != expected_svg:
            raise ValueError(f"Regenerated SVG differs: {stem}")
        pdf = args.output / (stem + ".pdf")
        draw.export_pdf(content, pdf)
        draw.validate(content, pdf, expected_labels)
        (args.output / (stem + ".svg")).write_text(content, encoding="utf8", newline="\n")
        records.append({"figure": stem, "svg_identical": True,
                        "pdf_labels_and_vector_content_checked": True,
                        "pdf_sha256": sha256(pdf.read_bytes()).hexdigest()})
    (args.output / "verification.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf8")
    print(json.dumps(records))


if __name__ == "__main__":
    main()
