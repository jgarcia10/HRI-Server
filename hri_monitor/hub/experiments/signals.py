"""Map a bus message (topic, data) to tidy CSV rows (signal, value). Pure."""

RECORDED_TOPICS = {
    "shimmer.gsr", "shimmer.ppg", "ppg.hr", "ppg.hrv",
    "rgb.blink", "thermal.temps", "model.estimates",
    "task.countdown", "task.step", "task.order_started",
    "task.part_placed", "task.perturbation",
    "wizard.reposition", "wizard.speech", "wizard.request_part", "wizard.slot_cleared",
    "wizard.mat_cleared",
    "robot.skill_done", "robot.part_staged", "robot.skill_failed", "robot.estop",
    "robot.rejected", "robot.resumed",
    "supply.decision", "supply.blocked",
    "anima.perception", "anima.verdict", "anima.error",
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
    if topic in ("task.part_placed", "task.perturbation", "wizard.reposition", "wizard.speech",
                 "wizard.request_part", "wizard.slot_cleared", "wizard.mat_cleared",
                 "supply.decision", "supply.blocked"):
        return [(topic, 1.0)]
    if topic == "robot.skill_done":
        # I4: one series per skill — mixing set_pace/home/supply makes the M4 "supply cycle
        # <= 5 s p95" criterion (spec 3.6) impossible to compute.
        return [(f"robot.{data.get('skill', 'skill')}_duration_s", float(data["duration_s"]))]
    if topic in ("robot.part_staged", "robot.skill_failed", "robot.estop",
                 "robot.rejected", "robot.resumed"):
        return [(topic, 1.0)]
    if topic == "anima.perception":
        rows = [(f"anima.{n}_pull", float(data[f"{n}_pull"])) for n in
                ("relatedness", "competence", "autonomy", "resource") if f"{n}_pull" in data]
        rows.append(("anima.intensity", float(data["intensity"])))
        regimes = ("supportive", "adversarial", "exploratory")
        if data.get("regime") in regimes:
            rows.append(("anima.regime_idx", float(regimes.index(data["regime"]))))
        return rows
    if topic == "anima.verdict":
        return [("anima.g", float(data["g"]))]
    if topic == "anima.error":
        return [("anima.error", 1.0)]
    return []
