"""Map a bus message (topic, data) to tidy CSV rows (signal, value). Pure."""

RECORDED_TOPICS = {
    "shimmer.gsr", "shimmer.ppg", "ppg.hr", "ppg.hrv",
    "rgb.blink", "thermal.temps", "model.estimates",
    "task.countdown", "task.step", "task.order_started",
    "task.part_placed", "task.perturbation",
    "wizard.reposition", "wizard.speech",
    "robot.skill_done", "robot.part_staged", "robot.skill_failed", "robot.estop",
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
    if topic == "task.countdown":
        return [("task.remaining_s", float(data["remaining_s"]))]
    if topic == "task.step":
        return [("task.step_index", float(data["step_index"]))]
    if topic == "task.order_started":
        return [("task.order_index", float(data["order_index"]))]
    if topic in ("task.part_placed", "task.perturbation", "wizard.reposition", "wizard.speech"):
        return [(topic, 1.0)]
    if topic == "robot.skill_done":
        return [("robot.skill_duration_s", float(data["duration_s"]))]
    if topic in ("robot.part_staged", "robot.skill_failed", "robot.estop"):
        return [(topic, 1.0)]
    return []
