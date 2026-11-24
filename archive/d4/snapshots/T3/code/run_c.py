"""C: frozen D3 neutral-prefix relation, with D4 case configuration."""
import argparse
import json
from common import select, save
from engine import test_pair


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cases")
    ap.add_argument("output")
    args = ap.parse_args()
    out = []
    for case in select(args.cases):
        result = test_pair(case)
        result["expected_status"] = case["expected_status"]
        result["reproduce"] = f"python run_c.py {args.cases} {args.output}"
        out.append(result)
    save(args.output, out)
    assert all(r["status"] == r["expected_status"] for r in out), [
        (r["name"], r["status"], r["expected_status"]) for r in out]
    print(json.dumps({"count": len(out), "statuses": [r["status"] for r in out]}))


if __name__ == "__main__":
    main()
