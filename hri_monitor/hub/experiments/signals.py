"""Map a bus message (topic, data) to tidy CSV rows (signal, value). Pure."""

RECORDED_TOPICS = {
    "shimmer.gsr", "shimmer.ppg", "ppg.hr", "ppg.hrv",
    "rgb.blink", "thermal.temps", "model.estimates",
}
_THERMAL_ROIS = ("forehead", "left_cheek", "right_cheek", "nose")


def sample_rows(topic: str, data: dict) -> list[tuple[str, float]]:
    """Return [(signal, value), ...] for one bus message; [] for un-recorded topics."""
    if topic in ("shimmer.gsr", "shimmer.ppg", "ppg.hr", "ppg.hrv"):
        return [(topic, float(data["value"]))]
    if topic == "rgb.blink":
        return [("rgb.blink", float(data["rate"]))]
    if topic == "thermal.temps":
        return [(f"thermal.{roi}", float(data[roi])) for roi in _THERMAL_ROIS if roi in data]
    if topic == "model.estimates":
        out = []
        if "cognitive_load" in data:
            out.append(("model.cognitive_load", float(data["cognitive_load"])))
        if "trust" in data:
            out.append(("model.trust", float(data["trust"])))
        return out
    return []
