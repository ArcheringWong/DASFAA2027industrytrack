"""Create the four-step technical diagram and verify it against saved product runs."""

import ast
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from tempfile import TemporaryDirectory


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PRIMITIVES = ROOT / "DASFAA2027_Industry_Final/latex/figures/prepare_industry_figures.py"
EVIDENCE = ROOT / "D_checkpoint_safety"
BASE = "figure2_early_stop_paths"
W, H = 460, 282
SMALL_FONT = 10.25


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_evidence():
    used = set()

    def read(path):
        used.add(path)
        return json.loads(path.read_bytes())

    fixture = EVIDENCE / "run_dlt_repro.py"
    used.add(fixture)
    parsed = ast.parse(fixture.read_text(encoding="utf-8-sig"))
    tuples = [node for node in ast.walk(parsed) if isinstance(node, ast.Tuple) and node.elts
              and isinstance(node.elts[0], ast.Constant) and node.elts[0].value == "issue_4523"]
    expected_fixture = ("issue_4523", [[{"id": 1, "ts": 2}]],
                        [[{"id": 1, "ts": 2}], [{"id": 2, "ts": 2}]], "desc", "closed")
    require(len(tuples) == 1 and ast.literal_eval(tuples[0]) == expected_fixture, "Dictionary fixture differs")
    for version, requests, rows in (("1.31.0", [1], [[1, 2]]), ("1.32.0", [1, 2], [[1, 2], [2, 2]])):
        trace = read(EVIDENCE / "evidence" / f"dlt_{version.replace('.', '_')}.json")
        case = next(row for row in trace["cases"] if row["case"] == "issue_4523")
        require(trace["dlt_version"] == version and case["first_pages"] == [1] and
                case["second_pages"] == requests and case["rows"] == rows, "Dictionary run differs")
    for version in ("1.29.0", "1.32.0"):
        trace = read(EVIDENCE / "D2_cross_mechanism/evidence" / f"calibrate_{version}_pipeline.json")
        for mode, requests, target in (("issue", [1], []), ("no_order", [1, 2], [3, 4])):
            case = next(row for row in trace if row["mode"] == mode)
            require(case["dlt_version"] == version and case["error"] is None and
                    case["source_batches"] == [{"id": [1, 2], "ts": [None, None]}, {"id": [3, 4], "ts": [5, 6]}] and
                    case["requested_batches"] == requests and case["expected_ids"] == [3, 4] and
                    case["output_ids"] == target, "Arrow run differs")
    calibration = EVIDENCE / "D2_cross_mechanism/calibrate_arrow.py"
    used.add(calibration)
    source = calibration.read_text(encoding="utf-8-sig")
    require("initial_value=0, end_value=10" in source and 'on_cursor_value_missing="exclude"' in source
            and 'None if mode == "no_order" else "asc"' in source, "Arrow read settings differ")
    for version, token in (
        ("131", "if unique_value in self.start_unique_hashes: return None, True, False"),
        ("132", "end_out_of_range = not self.end_compare(row_value_scalar, end_value_scalar).as_py()"),
    ):
        transform = EVIDENCE / "D5_runtime_guard/evidence" / f"source_{version}/transform.py"
        used.add(transform)
        require(token in " ".join(transform.read_text(encoding="utf-8").split()), "Archived stop flag differs")
    return used


def layout(draw):
    panels = (
        ("A  Dictionary · closed start", "dlt 1.31.0 · descending", "Prior confirmed (id=1, c=2)", (
            ("Page 1 · (id=1, c=2) deduplicated", "No new row emitted"),
            ("start_out_of_range = True", "Read closes"),
            ("Page 2 · new (id=2, c=2)", "Never requested"),
            ("Required {1,2} · actual {1}", "Requested [1]"),
        ), ("Fixed release · dlt 1.32.0", "Requests [1,2] · loads {1,2}")),
        ("B  Arrow · open end", "dlt 1.29.0 / 1.32.0 · ascending", "Range [0,10) · null=exclude", (
            ("Batch 1 · (id=1, NULL), (id=2, NULL)", "Both rows excluded"),
            ("Null comparison flags end crossing", "Read closes"),
            ("Batch 2 · (id=3, c=5), (id=4, c=6)", "Never requested"),
            ("Required {3,4} · actual ∅", "Requested [1]"),
        ), ("Control · without row_order", "Requests [1,2] · loads {3,4}")),
    )
    steps = ("1  Valid local filtering", "2  Incorrect source stop",
             "3  Eligible unread suffix", "4  Successful run, missing IDs")
    positions = (48, 99, 150, 201)
    styles = (("#ffffff", "#647d8e", False), ("#fff3f1", "#a84333", False),
              ("#ffffff", "#a84333", True), ("#eaf0f4", "#526b7b", False))
    out, labels = [], []
    for x, (heading, version, scope, rows, control) in zip((2, 232), panels, strict=True):
        out.append(draw.rect(x, 2, 226, 278, "#fafbfd", "#a3b1ba"))

        def label(value, y, size=SMALL_FONT, bold=False):
            labels.append(value)
            out.append(draw.text(value, x + 11, y, 204, size=size, bold=bold, max_lines=1))

        label(heading, 17, size=12, bold=True)
        label(version, 30)
        label(scope, 42)
        for i, (y, style, stage, body) in enumerate(zip(positions, styles, steps, rows, strict=True)):
            out.append(draw.rect(x + 6, y, 214, 42, *style))
            label(stage, y + 13, size=11, bold=True)
            label(body[0], y + 27)
            label(body[1], y + 38)
            if i < 3:
                out.append(draw.arrow(x + 113, y + 43, x + 113, positions[i + 1] - 1))
        label(control[0], 257, size=10.5, bold=True)
        label(control[1], 271)
    return draw.diagram(W, H, out), labels


def checksum(file):
    return sha256(file.read_bytes()).hexdigest()


def main():
    sources = check_evidence()
    spec = spec_from_file_location("industry_vector_primitives", PRIMITIVES)
    draw = module_from_spec(spec)
    spec.loader.exec_module(draw)
    for name, file in (("Arial", "arial.ttf"), ("Arial-Bold", "arialbd.ttf"), ("Segoe-UI-Symbol", "seguisym.ttf")):
        draw.pdfmetrics.registerFont(draw.TTFont(name, str(draw.FONT_DIR / file)))
    svg, labels = layout(draw)
    with TemporaryDirectory(prefix="dasfaa-figure-") as tmp:
        temporary = Path(tmp) / (BASE + ".pdf")
        draw.export_pdf(svg, temporary)
        draw.validate(svg, temporary, labels)
        pdf_path = OUT / temporary.name
        pdf_path.write_bytes(temporary.read_bytes())
    svg_path = OUT / (BASE + ".svg")
    svg_path.write_text(svg, encoding="utf-8", newline="\n")
    sources.add(PRIMITIVES)
    receipt = {"caption_number_assigned_by_manuscript": 1, "pdf_width_pt": W * .75, "pdf_height_pt": H * .75,
               "minimum_font_pt": SMALL_FONT * .75, "steps_per_panel": 4, "raster_images": 0,
               "validated_labels": labels,
               "sources_sha256": {p.relative_to(ROOT).as_posix(): checksum(p) for p in sorted(sources)},
               "outputs_sha256": {p.name: checksum(p) for p in (pdf_path, svg_path)}}
    (OUT / "early-stop-figure-verification.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                                                            encoding="utf-8", newline="\n")
    print(receipt["outputs_sha256"])


if __name__ == "__main__":
    main()
