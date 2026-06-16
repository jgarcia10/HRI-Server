"""Condition-comparison engine: gather feature values per condition, aggregate to
the unit of analysis, auto-detect pairing, and run the auto-selected pingouin test."""
from collections import defaultdict

from .features import extract_features


def gather(db, experiment_id, condition_ids, signal, feature, unit):
    """Return {rows: [{subject, condition_id, value}], paired: bool, counts: {cond: n}}.

    rows are one value per unit of analysis. `subject` is the participant id
    (per-participant: aggregated; per-recording: still the participant, but each
    recording is its own row). Pairing = per-participant AND identical participant
    set across all conditions (complete cases only)."""
    recs = db.recordings_for_conditions(experiment_id, condition_ids)
    # condition -> participant -> [feature values across that participant's recordings]
    per = defaultdict(lambda: defaultdict(list))
    recording_rows = []  # for the per-recording unit
    for r in recs:
        f = extract_features(r["csv_path"], signal)
        if f is None or feature not in f:
            continue
        v = f[feature]
        per[r["condition_id"]][r["participant_id"]].append(v)
        recording_rows.append({"subject": r["participant_id"], "condition_id": r["condition_id"], "value": v})

    if unit == "recording":
        counts = defaultdict(int)
        for row in recording_rows:
            counts[row["condition_id"]] += 1
        return {"rows": recording_rows, "paired": False, "counts": dict(counts)}

    # per-participant: average within (participant, condition)
    rows = []
    sets = []
    for cid in condition_ids:
        subjects = per.get(cid, {})
        sets.append(set(subjects))
        for pid, vals in subjects.items():
            rows.append({"subject": pid, "condition_id": cid, "value": sum(vals) / len(vals)})
    paired = len(sets) >= 2 and len(sets[0]) > 0 and all(s == sets[0] for s in sets)
    if paired:
        common = set.intersection(*sets)
        rows = [r for r in rows if r["subject"] in common]
    counts = defaultdict(int)
    for r in rows:
        counts[r["condition_id"]] += 1
    return {"rows": rows, "paired": paired, "counts": dict(counts)}
