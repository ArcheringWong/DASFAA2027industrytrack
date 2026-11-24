"""Verify package hashes and recorded validation invariants using the standard library."""

import json
from hashlib import sha256
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    manifest = read("MANIFEST.json")
    for item in manifest["files"]:
        path = (ROOT / item["path"]).resolve()
        require(path.is_relative_to(ROOT), "Manifest path outside package")
        require(sha256(path.read_bytes()).hexdigest() == item["sha256"],
                f"Hash mismatch: {item['path']}")
    old = read("validation/witnesses-1.31.0.json")
    new = read("validation/witnesses-1.32.0.json")
    require(old["all_pass"] and new["all_pass"], "Witness acceptance failed")
    require(len(old["records"]) == 1 and len(new["records"]) == 3, "Witness records missing")
    a_old = old["records"][0]["rounds"][-1]
    a_new = new["records"][0]["rounds"][-1]
    require(a_old["target_ids"] == a_old["requested_pages"] == [1], "Old dictionary trace changed")
    require(a_new["target_ids"] == a_new["requested_pages"] == [1, 2], "Fix control trace changed")
    b, control = new["records"][1:]
    require(b["target_ids"] == [] and b["requested_batches"] == [1], "Arrow omission trace changed")
    require(control["target_ids"] == [3, 4] and control["requested_batches"] == [1, 2],
            "Arrow configuration control changed")
    for version, expected in (("1.31.0", 1), ("1.32.0", 11)):
        result = read(f"validation/oracle-{version}.json")
        require(result["environment"]["dlt"] == version, "Wrong Oracle environment")
        require(result["tested"] == result["passed"] == expected, "Oracle acceptance failed")
        require(all(case["pass"] for case in result["tests"]), "A boundary assertion failed")
    print(json.dumps({"package_files_verified": len(manifest["files"]),
                      "witness_records": 4, "oracle_assertions": 12, "pass": True}))


if __name__ == "__main__":
    main()
