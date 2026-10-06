import math
from datetime import date


def _to_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def progression(visits: list[dict]) -> dict:
    """Longitudinal trend of lesion size across dated visits (P13).

    Linear growth between first and last measured visit. Threshold of 1mm on
    size change separates stable from growing/shrinking (measurement noise).
    """
    measured = sorted(
        (v for v in visits if v.get("size_mm") is not None),
        key=lambda v: _to_date(v["visit_date"]),
    )
    series = [
        {"date": str(_to_date(v["visit_date"])), "size_mm": float(v["size_mm"])}
        for v in measured
    ]
    if len(measured) < 2:
        return {
            "trend": "unknown",
            "delta_mm": None,
            "doubling_time_days": None,
            "growth_mm_per_day": None,
            "series": series,
        }
    first, last = series[0], series[-1]
    delta = round(last["size_mm"] - first["size_mm"], 2)
    days = (_to_date(last["date"]) - _to_date(first["date"])).days
    rate = delta / days if days > 0 else 0.0
    trend = "growing" if delta > 1.0 else ("shrinking" if delta < -1.0 else "stable")
    doubling = None
    if rate > 0 and first["size_mm"] > 0:
        doubling = round(math.log(2) / rate, 1)
    return {
        "trend": trend,
        "delta_mm": delta,
        "doubling_time_days": doubling,
        "growth_mm_per_day": round(rate, 4),
        "series": series,
    }
