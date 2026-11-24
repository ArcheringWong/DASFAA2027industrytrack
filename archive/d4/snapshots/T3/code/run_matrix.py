"""Run the three D4 test organizations against both real pinned dlt releases."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot", choices=["base", "T1", "T2", "T3"])
    ap.add_argument("--explore-b", action="store_true")
    ap.add_argument("--only", choices=["a", "b", "c"])
    args = ap.parse_args()
    manifest_path = ROOT / "evidence" / args.snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if args.only and manifest_path.exists() else []
    for version, venv in (("1.31.0", "131"), ("1.32.0", "132")):
        python = ROOT / f".venv_{venv}" / "Scripts" / "python.exe"
        for scheme in ("a", "b", "c"):
            if args.only and scheme != args.only:
                continue
            case_file = ROOT / "snapshots" / args.snapshot / f"{scheme}_cases.json"
            output = ROOT / "evidence" / args.snapshot / f"{scheme}_{version}.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists():
                output.unlink()
            env = os.environ.copy()
            env["D4_CASE_FILE"] = str(case_file)
            env["D4_RESULT_FILE"] = str(output)
            if scheme == "a":
                cmd = [str(python), "-m", "pytest", "test_a.py", "-q", "--disable-warnings"]
            elif scheme == "b":
                cmd = [str(python), "stateful_b.py", str(case_file), str(output)]
                if args.explore_b:
                    cmd.append("--explore")
            else:
                cmd = [str(python), "run_c.py", str(case_file), str(output)]
            start = time.perf_counter()
            run = subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True)
            elapsed = round(time.perf_counter() - start, 6)
            log = ROOT / "evidence" / args.snapshot / f"{scheme}_{version}.log"
            log.write_text("COMMAND: " + subprocess.list2cmdline(cmd) + "\nEXIT: " + str(run.returncode)
                           + "\nSTDOUT:\n" + run.stdout + "\nSTDERR:\n" + run.stderr,
                           encoding="utf-8")
            item = {"snapshot": args.snapshot, "scheme": scheme, "version": version,
                    "exit_code": run.returncode, "wall_seconds": elapsed,
                    "case_file": str(case_file.relative_to(ROOT)), "result_file": str(output.relative_to(ROOT)),
                    "log_file": str(log.relative_to(ROOT)), "command": cmd}
            manifest = [prior for prior in manifest if not (prior["scheme"] == scheme and prior["version"] == version)]
            manifest.append(item)
            print(json.dumps({k: item[k] for k in ("snapshot", "scheme", "version", "exit_code", "wall_seconds")}))
            manifest_path.write_text(
                json.dumps(manifest, indent=2), encoding="utf-8")
            if run.returncode:
                raise SystemExit(f"{scheme} {version} failed; see {log}")


if __name__ == "__main__":
    main()
