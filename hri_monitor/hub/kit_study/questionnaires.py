"""Post-block self-report instruments: NASA-TLX (raw, 0-100) and the HRTS-style trust scale
(1-7). Item names and CSV columns match the Physio-HRC dataset
(`questionnaires/nasa_tlx.csv`, `questionnaires/trust_hrts.csv`) so analyses are reusable."""
from __future__ import annotations

import csv
import io

INSTRUMENTS: dict[str, dict] = {
    "nasa_tlx": {
        "title": "How did that round feel?",
        "scale": {"min": 0, "max": 100, "step": 5},
        "score": "overall_score",
        "items": [
            {"key": "mental_demand", "label": "Mental demand",
             "question": "How mentally demanding was the task?", "low": "Very low", "high": "Very high"},
            {"key": "physical_demand", "label": "Physical demand",
             "question": "How physically demanding was the task?", "low": "Very low", "high": "Very high"},
            {"key": "temporal_demand", "label": "Temporal demand",
             "question": "How hurried or rushed was the pace of the task?", "low": "Very low", "high": "Very high"},
            {"key": "performance", "label": "Performance",
             "question": "How successful were you in accomplishing what you were asked to do?",
             "low": "Perfect", "high": "Failure"},
            {"key": "effort", "label": "Effort",
             "question": "How hard did you have to work to accomplish your level of performance?",
             "low": "Very low", "high": "Very high"},
            {"key": "frustration", "label": "Frustration",
             "question": "How insecure, discouraged, irritated, stressed and annoyed were you?",
             "low": "Very low", "high": "Very high"},
        ],
    },
    "trust_hrts": {
        "title": "How much did you trust the robot?",
        "scale": {"min": 1, "max": 7, "step": 1},
        "score": "overall_trust",
        "items": [
            {"key": "reliability", "label": "Reliability",
             "question": "The robot delivered the pieces reliably.", "low": "Strongly disagree", "high": "Strongly agree"},
            {"key": "competence", "label": "Competence",
             "question": "The robot was competent at its part of the task.", "low": "Strongly disagree", "high": "Strongly agree"},
            {"key": "predictability", "label": "Predictability",
             "question": "I could predict what the robot would do next.", "low": "Strongly disagree", "high": "Strongly agree"},
            {"key": "transparency", "label": "Transparency",
             "question": "It was clear to me why the robot did what it did.", "low": "Strongly disagree", "high": "Strongly agree"},
        ],
    },
}
ORDER = ("nasa_tlx", "trust_hrts")


def validate(instrument: str, answers: dict) -> dict[str, float]:
    """Return {item_key: value} with every item present and inside the scale, else ValueError."""
    if instrument not in INSTRUMENTS:
        raise ValueError(f"unknown instrument {instrument!r}; expected one of {ORDER}")
    spec = INSTRUMENTS[instrument]
    lo, hi = spec["scale"]["min"], spec["scale"]["max"]
    out = {}
    for item in spec["items"]:
        k = item["key"]
        if k not in answers:
            raise ValueError(f"{instrument}: missing answer for {k}")
        try:
            v = float(answers[k])
        except (TypeError, ValueError):
            raise ValueError(f"{instrument}: {k} must be a number") from None
        if not lo <= v <= hi:
            raise ValueError(f"{instrument}: {k}={v} outside {lo}-{hi}")
        out[k] = v
    return out


def score(instrument: str, answers: dict[str, float]) -> float:
    """Raw (unweighted) mean of the items — the dataset's overall_score / overall_trust."""
    keys = [i["key"] for i in INSTRUMENTS[instrument]["items"]]
    return round(sum(answers[k] for k in keys) / len(keys), 2)


def to_csv(instrument: str, rows: list[dict]) -> str:
    """Dataset layout: participant_id, condition, <items…>, <score column>. Skipped rows omitted."""
    spec = INSTRUMENTS[instrument]
    keys = [i["key"] for i in spec["items"]]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["participant_id", "condition", *keys, spec["score"]])
    for r in rows:
        a = r["answers"]
        if a.get("skipped") or r.get("score") is None:
            continue
        w.writerow([r["participant_code"], r["condition_name"], *[a[k] for k in keys], r["score"]])
    return buf.getvalue()
