"""Distillation helpers (kept for interface compatibility; no SQL evaluation)."""


def distinct_share(values) -> float:
    """Share of duplicate values in a list (0.0 if empty)."""
    if not values:
        return 0.0
    return 1.0 - len(set(values)) / float(len(values))
