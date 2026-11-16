"""Neighbour helpers for boundary literals (case-flip / single-character edits)."""
import string


def case_flip(rng, v: str) -> str:
    """Flip one or all letters' case."""
    if not v:
        return v
    if rng.random() < 0.5:
        return v.lower() if any(c.isupper() for c in v) else v.upper()
    i = rng.randrange(len(v))
    c = v[i]
    nc = c.lower() if c.isupper() else (c.upper() if c.islower() else c)
    return v[:i] + nc + v[i + 1:]


def single_char_edit(rng, v: str) -> str:
    """Drop, replace or duplicate one character."""
    if not v:
        return v
    u = rng.random()
    i = rng.randrange(len(v))
    if u < 0.34:
        return v[:i] + v[i + 1:]
    if u < 0.67:
        return v[:i] + rng.choice(string.ascii_uppercase) + v[i + 1:]
    return v[:i] + v[i] + v[i:]


def variants(rng, v: str, k: int = 4) -> list:
    """Return up to k near-variants of v (case-flip / single-character edits)."""
    out = []
    for _ in range(k):
        out.append(case_flip(rng, v) if rng.random() < 0.5 else single_char_edit(rng, v))
    return out
