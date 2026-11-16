"""Comparison helpers (kept for interface compatibility; no SQL evaluation)."""


def equal_and_one_step(values, target):
    """Return values equal to target or one step away (numeric)."""
    out = []
    for v in values:
        try:
            if v == target or abs(float(v) - float(target)) <= 1:
                out.append(v)
        except (TypeError, ValueError):
            if v == target:
                out.append(v)
    return out
