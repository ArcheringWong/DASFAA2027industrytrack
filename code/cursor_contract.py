"""Source-side eligibility for the integer max-cursor fixtures."""


def end_mode(mode):
    if mode not in ("open", "closed"):
        raise ValueError(f"invalid range_end: {mode!r}")
    return mode


def eligible(cursor, start, end, mode, missing_policy="exclude"):
    if cursor is None:
        return missing_policy == "include"
    return cursor >= start and (
        end is None or cursor < end or (mode == "closed" and cursor == end)
    )
