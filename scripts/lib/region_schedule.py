"""Load Region of Waterloo household schedule by area key."""

from __future__ import annotations

from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEDULE = (
    ROOT / "corpus" / "region-of-waterloo-on" / "schedules" / "household-tax-supported-2026.yaml"
)

AREA_KEYS = ("blended", "urban", "rural", "woolwich", "wilmot")

AREA_LABELS = {
    "blended": "Blended Regional",
    "urban": "Urban (Kitchener / Waterloo / Cambridge)",
    "rural": "Rural (North Dumfries / Wellesley)",
    "woolwich": "Woolwich",
    "wilmot": "Wilmot",
}


def load_region_schedule(
    area_key: str,
    schedule_path: Path | None = None,
) -> dict:
    """Return {source, area, assessmentCad, page, extractPath, areaKey, areaLabel}."""
    if yaml is None:
        raise SystemExit("PyYAML required (pip install pyyaml)")
    if area_key not in AREA_KEYS:
        raise SystemExit(f"unknown regionAreaKey {area_key!r}; expected one of {AREA_KEYS}")
    path = schedule_path or DEFAULT_SCHEDULE
    if not path.exists():
        raise SystemExit(
            f"missing {path}\nRun: python scripts/parse_row_household_schedule.py"
        )
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    area = doc["areas"][area_key]
    src = doc["source"]
    return {
        "source": src,
        "area": area,
        "areaKey": area_key,
        "areaLabel": AREA_LABELS[area_key],
        "assessmentCad": src["assessmentCad"],
        "page": src["pdfPage"],
        "extractPath": src["extractPath"],
    }
