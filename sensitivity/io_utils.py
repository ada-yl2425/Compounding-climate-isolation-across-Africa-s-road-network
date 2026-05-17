"""Small I/O helpers shared by robustness scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_csv(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path, **kwargs)


def write_table(df: pd.DataFrame, path: Path, index: bool = False) -> Path:
    ensure_dir(path.parent)
    df.to_csv(path, index=index)
    return path


def write_json(obj: dict, path: Path) -> Path:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")
    return path


def finite_numeric(series: pd.Series, fill: float = 0.0) -> pd.Series:
    out = pd.to_numeric(series, errors="coerce")
    out = out.replace([np.inf, -np.inf], np.nan)
    return out.fillna(fill)


def normalize_positive(series: pd.Series) -> pd.Series:
    s = finite_numeric(series)
    pos = s[s > 0]
    if pos.empty:
        return s * 0.0
    return (s / float(pos.max())).clip(lower=0.0)


def top_set(scores: pd.Series, k: int) -> set[int]:
    if k <= 0 or scores.empty:
        return set()
    return set(scores.nlargest(min(k, len(scores))).index.astype(int))


def jaccard(a: Iterable[int], b: Iterable[int]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    mask = values.notna() & weights.notna() & (weights > 0)
    if not mask.any():
        return float("nan")
    return float(np.average(values[mask], weights=weights[mask]))
