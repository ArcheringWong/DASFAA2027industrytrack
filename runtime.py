"""Keep validation state local and select an explicitly supplied dependency tree."""

import os
from pathlib import Path
import site
import sys


def prepare(args, work):
    for path in reversed(args.dependency_path):
        directory = str(Path(path).resolve())
        site.addsitedir(directory)
        sys.path.remove(directory)
        sys.path.insert(1, directory)
    os.environ["RUNTIME__DLTHUB_TELEMETRY"] = "false"
    os.environ["DLT_DATA_DIR"] = str(work / "settings")
    import dlt
    from dlt.common.runtime import run_context

    if dlt.__version__ != args.version:
        raise RuntimeError(f"Expected dlt {args.version}, found {dlt.__version__}")
    global_config = work / "global"
    global_config.mkdir()
    run_context.global_dir = lambda: str(global_config)
    return dlt


def arguments(parser):
    parser.add_argument("--version", required=True, choices=("1.31.0", "1.32.0"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dependency-path", action="append", default=[],
                        help="Optional existing package directory. Earlier paths take precedence.")
