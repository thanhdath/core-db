"""Greedy test-suite distillation (paper section 3.2; no upstream code)."""


def distill_instances(kills: dict, neighbors: dict, max_keep=None) -> list:
    """Greedy set cover: keep the unit killing most not-yet-killed neighbours, ties -> smallest id."""
    targets = {n for ids in neighbors.values() for n in ids}
    killed: set = set()
    kept: list = []
    while max_keep is None or len(kept) < max_keep:
        best, gain = None, 0
        for u in sorted(kills):
            if u in kept:
                continue
            g = len((set(kills[u]) & targets) - killed)
            if g > gain:
                best, gain = u, g
        if best is None:
            break
        kept.append(best)
        killed |= set(kills[best]) & targets
    return kept
