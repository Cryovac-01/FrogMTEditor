"""Shared weighted torque-based engine pricing helpers."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Iterable, Sequence


REFERENCE_PRICE_ENGINE = 'V12_789HP'
REFERENCE_PRICE = 20000
MIN_ENGINE_PRICE = 1000
MAX_ENGINE_PRICE = 100000


@dataclass(frozen=True)
class TorquePricePoint:
    torque_nm: float
    rank_fraction: float


@dataclass(frozen=True)
class TorquePriceModel:
    points: tuple[TorquePricePoint, ...]
    reference_engine: str
    reference_torque_nm: float
    reference_rank_fraction: float
    min_price: int = MIN_ENGINE_PRICE
    reference_price: int = REFERENCE_PRICE
    max_price: int = MAX_ENGINE_PRICE


def _collapse_torque_points(sorted_torques: Sequence[float]) -> tuple[TorquePricePoint, ...]:
    """Collapse duplicate torque values into unique points with averaged rank."""
    if not sorted_torques:
        return tuple()
    if len(sorted_torques) == 1:
        return (TorquePricePoint(float(sorted_torques[0]), 0.0),)

    points: list[TorquePricePoint] = []
    last_index = len(sorted_torques) - 1
    i = 0
    while i < len(sorted_torques):
        torque_nm = float(sorted_torques[i])
        start = i
        while i + 1 < len(sorted_torques) and sorted_torques[i + 1] == torque_nm:
            i += 1
        end = i
        rank_fraction = ((start + end) / 2.0) / last_index
        points.append(TorquePricePoint(torque_nm, rank_fraction))
        i += 1
    return tuple(points)


def _point_torques(model: TorquePriceModel) -> list[float]:
    return [point.torque_nm for point in model.points]


def percentile_for_torque(model: TorquePriceModel, torque_nm: float) -> float:
    """Return a weighted percentile rank for an arbitrary torque value."""
    if not model.points:
        return 0.0

    value = float(torque_nm)
    first = model.points[0]
    last = model.points[-1]
    if value <= first.torque_nm:
        return 0.0
    if value >= last.torque_nm:
        return 1.0

    point_torques = _point_torques(model)
    pos = bisect_left(point_torques, value)
    if pos < len(model.points) and model.points[pos].torque_nm == value:
        return model.points[pos].rank_fraction

    lower = model.points[pos - 1]
    upper = model.points[pos]
    span = upper.torque_nm - lower.torque_nm
    if span <= 0:
        return upper.rank_fraction

    ratio = (value - lower.torque_nm) / span
    return lower.rank_fraction + ((upper.rank_fraction - lower.rank_fraction) * ratio)


def build_torque_price_model(specs: Iterable[object],
                             reference_engine: str = REFERENCE_PRICE_ENGINE) -> TorquePriceModel:
    """Build a weighted price curve from objects exposing name and torque_nm."""
    specs = list(specs)
    if not specs:
        raise ValueError('Cannot build a price model without template specs')

    torques = sorted(float(spec.torque_nm) for spec in specs)
    reference_torque = None
    for spec in specs:
        if getattr(spec, 'name', None) == reference_engine:
            reference_torque = float(spec.torque_nm)
            break
    if reference_torque is None:
        raise ValueError(f'Reference price engine not found: {reference_engine}')

    points = _collapse_torque_points(torques)
    model = TorquePriceModel(
        points=points,
        reference_engine=reference_engine,
        reference_torque_nm=reference_torque,
        reference_rank_fraction=0.0,
    )
    return TorquePriceModel(
        points=points,
        reference_engine=reference_engine,
        reference_torque_nm=reference_torque,
        reference_rank_fraction=percentile_for_torque(model, reference_torque),
    )


def recommend_price_from_torque(model: TorquePriceModel, torque_nm: float) -> int:
    """Recommend a shop price from torque using the weighted percentile curve.

    Formula:
      1. Convert torque to percentile rank within the curated template distribution.
      2. Interpolate from weakest -> Ferrari anchor -> strongest:
         weakest = 1000, Ferrari F140GA = 20000, strongest = 100000.
    """
    percentile = percentile_for_torque(model, torque_nm)

    if percentile <= model.reference_rank_fraction:
        segment = 0.0 if model.reference_rank_fraction <= 0 else percentile / model.reference_rank_fraction
        price = model.min_price + ((model.reference_price - model.min_price) * segment)
    else:
        tail_span = 1.0 - model.reference_rank_fraction
        segment = 1.0 if tail_span <= 0 else (percentile - model.reference_rank_fraction) / tail_span
        price = model.reference_price + ((model.max_price - model.reference_price) * segment)

    return max(model.min_price, min(model.max_price, int(round(price))))
