"""Similarity score between two SQL execution results."""
from __future__ import annotations
from typing import Any, Dict, List, Optional

import pandas as pd  # type: ignore


class SQLExecScorer:
    """Score similarity between two SQL execution results (GT vs Prediction) in [0, 1]."""

    def __init__(self, *, alpha: float = 0.5, gamma: float = 1.2,
                 mode: str = "rankcorr", numeric_eps: float = 1e-6):
        """Args:"""
        assert mode in ("rankcorr", "footrule")
        self.alpha = float(alpha)
        self.gamma = float(gamma)
        self.mode = mode
        self.numeric_eps = float(numeric_eps)

    def score_from_rows(self,
                        gt_rows: Optional[List[Dict[str, Any]]],
                        pred_rows: Optional[List[Dict[str, Any]]]) -> float:
        """Compute the score given raw row objects (list of dicts) from the executor."""
        gt_df = _rows_to_dataframe(gt_rows)
        pr_df = _rows_to_dataframe(pred_rows)
        if gt_df is None or pr_df is None:
            return 0.0

        gt_cols = list(gt_df.columns)
        pr_cols = list(pr_df.columns)
        if set(gt_cols) != set(pr_cols):
            return 0.0

        pr_df = pr_df[gt_cols]

        gt_seq = self._df_to_row_seq(gt_df, gt_cols)
        pr_seq = self._df_to_row_seq(pr_df, gt_cols)

        cov = self._coverage(gt_seq, pr_seq)

        ord_score = self._order_score(gt_seq, pr_seq, mode=self.mode)

        R = (cov ** self.gamma) * (self.alpha * ord_score + (1.0 - self.alpha))
        return max(0.0, min(1.0, float(R)))

    def _normalize_value(self, v: Any):
        """Normalize cell values for robust equality:"""
        if isinstance(v, (int, float)):
            return round(float(v), self._decimals_for_eps(self.numeric_eps))
        s = str(v)
        try:
            f = float(s)
            return round(f, self._decimals_for_eps(self.numeric_eps))
        except Exception:
            pass
        return s.strip().lower()

    @staticmethod
    def _decimals_for_eps(eps: float) -> int:
        """Convert eps (e.g., 1e-6) into a practical rounding precision."""
        if eps <= 0:
            return 6
        import math
        d = max(0, int(round(-math.log10(eps))))
        return min(9, max(0, d))

    def _df_to_row_seq(self, df: pd.DataFrame, cols: List[str]) -> List[tuple]:
        """Convert a DataFrame slice (cols already aligned) into a list of normalized row tuples."""
        rows = []
        for _, r in df.iterrows():
            tup = tuple(self._normalize_value(r[c]) for c in cols)
            rows.append(tup)
        return rows

    @staticmethod
    def _coverage(a_seq: List[tuple], b_seq: List[tuple]) -> float:
        """Multiset overlap of rows divided by max(len(a), len(b))."""
        from collections import Counter
        A, B = Counter(a_seq), Counter(b_seq)
        inter = sum(min(A[k], B[k]) for k in A.keys() & B.keys())
        denom = max(len(a_seq), len(b_seq), 1)
        return inter / float(denom)

    @staticmethod
    def _make_occ_keys(seq: List[tuple]) -> List[tuple]:
        """Expand duplicate rows into unique tokens using occurrence indices."""
        from collections import defaultdict
        counts = defaultdict(int)
        out = []
        for t in seq:
            k = (t, counts[t])
            counts[t] += 1
            out.append(k)
        return out

    def _common_unique_tokens(self, a_seq: List[tuple], b_seq: List[tuple]):
        """Build duplicate-aware tokens for both sequences and take their intersection."""
        A = self._make_occ_keys(a_seq)
        B = self._make_occ_keys(b_seq)
        common = list(set(A) & set(B))
        return A, B, common

    def _order_score(self, gt_seq: List[tuple], pr_seq: List[tuple], *, mode: str) -> float:
        """Compute an order score on the intersection of duplicate-aware tokens."""
        A, B, common = self._common_unique_tokens(pr_seq, gt_seq)
        k = len(common)
        if k <= 1:
            return 1.0

        rankA = {tok: idx for idx, tok in enumerate(A, start=1)}
        rankB = {tok: idx for idx, tok in enumerate(B, start=1)}

        ranksA = [rankA[t] for t in common]
        ranksB = [rankB[t] for t in common]

        if mode == "rankcorr":
            return self._spearman_norm(ranksA, ranksB)
        else:
            return self._footrule_norm(ranksA, ranksB)

    @staticmethod
    def _spearman_norm(rA: List[int], rB: List[int]) -> float:
        """Spearman's rho via squared rank differences:"""
        k = len(rA)
        if k <= 1:
            return 1.0
        d2 = sum((a - b) * (a - b) for a, b in zip(rA, rB))
        denom = k * (k * k - 1)
        if denom == 0:
            return 1.0
        rho = 1.0 - (6.0 * d2) / float(denom)
        return max(0.0, min(1.0, 0.5 * (rho + 1.0)))

    @staticmethod
    def _footrule_norm(rA: List[int], rB: List[int]) -> float:
        """Spearman footrule distance:"""
        k = len(rA)
        if k <= 1:
            return 1.0
        F = sum(abs(a - b) for a, b in zip(rA, rB))
        Fmax = (k * k) // 2
        if Fmax <= 0:
            return 1.0
        return max(0.0, min(1.0, 1.0 - (F / float(Fmax))))


def _rows_to_dataframe(rows: Optional[List[Dict[str, Any]]]) -> Optional[pd.DataFrame]:
    if rows is None:
        return None
    if not isinstance(rows, list):
        return None
    try:
        df = pd.DataFrame(rows)
        return df.fillna("")
    except Exception:
        return None
