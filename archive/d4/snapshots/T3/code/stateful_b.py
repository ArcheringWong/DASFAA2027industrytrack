"""B: explicit regression replay plus bounded Hypothesis state transitions."""
import argparse
import copy
import json
from pathlib import Path
from hypothesis import settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, precondition, rule, run_state_machine_as_test
from common import select, single, save


class ExtractionMachine(RuleBasedStateMachine):
    cases = []
    generated = []

    def __init__(self):
        super().__init__()
        self.current = None
        self.revision = 0

    @initialize(index=st.integers(min_value=0, max_value=20))
    def choose(self, index):
        self.current = copy.deepcopy(self.cases[index % len(self.cases)])

    @rule(index=st.integers(min_value=0, max_value=20))
    def choose_again(self, index):
        self.current = copy.deepcopy(self.cases[index % len(self.cases)])
        self.revision += 1

    @precondition(lambda self: self.current is not None and not self.current.get("invalid_reason"))
    @rule()
    def split_last_batch(self):
        batches = self.current["base_batches"]
        if batches and len(batches[-1]) > 1:
            last = batches.pop()
            batches.extend([[r] for r in last])
            self.revision += 1

    @precondition(lambda self: self.current is not None and not self.current.get("invalid_reason"))
    @rule()
    def coalesce_first_batches(self):
        batches = self.current["base_batches"]
        if len(batches) > 1:
            batches[:2] = [batches[0] + batches[1]]
            self.revision += 1

    @precondition(lambda self: self.current is not None and not self.current.get("invalid_reason"))
    @rule()
    def drop_excluded_null_prefix(self):
        batches = self.current["base_batches"]
        if batches and all(r["ts"] is None for r in batches[0]) and self.current["missing_policy"] == "exclude":
            batches.pop(0)
            self.revision += 1

    @invariant()
    def evaluate(self):
        if self.current is None or self.current.get("invalid_reason"):
            return
        if len(self.generated) >= 12:
            return
        result = single(self.current)
        result["generated_revision"] = self.revision
        self.generated.append(result)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cases")
    ap.add_argument("output")
    ap.add_argument("--explore", action="store_true")
    args = ap.parse_args()
    cases = select(args.cases)
    deterministic = []
    for case in cases:
        result = single(case)
        result["expected_status"] = case["expected_status"]
        result["reproduce"] = f"python stateful_b.py {args.cases} {args.output}"
        deterministic.append(result)
    generated = []
    if args.explore:
        base_names = {c["name"] for c in select(str(Path(__file__).resolve().parent / "snapshots" / "base" / "b_cases.json"))}
        ExtractionMachine.cases = ([c for c in cases if c["name"] not in base_names]
                                   + [c for c in cases if c["name"] in base_names])
        ExtractionMachine.generated = generated
        run_state_machine_as_test(ExtractionMachine, settings=settings(
            max_examples=4, stateful_step_count=3, deadline=None, derandomize=True))
    save(args.output, {"deterministic": deterministic, "state_machine_exploration": generated})
    assert all(r["status"] == r["expected_status"] for r in deterministic)
    print(json.dumps({"deterministic": len(deterministic), "generated": len(generated),
                      "statuses": [r["status"] for r in deterministic]}))


if __name__ == "__main__":
    main()
