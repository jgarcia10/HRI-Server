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
        try:
            f = extract_features(r["csv_path"], signal)
        except OSError:
            continue  # stale/missing/unreadable csv_path → skip this recording
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


import pandas as pd
import pingouin as pg

_MIN_PER_CONDITION = 3


def _magnitude(name, value):
    a = abs(value)
    if name == "cohen_d":
        return "large" if a >= 0.8 else "medium" if a >= 0.5 else "small"
    if name == "rank-biserial":
        return "large" if a >= 0.5 else "medium" if a >= 0.3 else "small"
    if name in ("partial eta^2", "generalized eta^2", "epsilon^2"):
        return "large" if a >= 0.14 else "medium" if a >= 0.06 else "small"
    if name == "Kendall W":
        return "large" if a >= 0.5 else "medium" if a >= 0.3 else "small"
    return "small"


def _descriptives(df, cond_names, normal_tbl):
    out = []
    for cid, sub in df.groupby("condition"):
        sp = float(normal_tbl.loc[cid, "pval"]) if cid in normal_tbl.index else None
        out.append({"condition": cond_names.get(cid, str(cid)), "n": int(len(sub)),
                    "mean": float(sub["value"].mean()), "sd": float(sub["value"].std(ddof=0)),
                    "shapiro_p": sp})
    return out


def run_test(g, condition_ids, cond_names):
    rows = g["rows"]
    counts = g["counts"]
    if any(counts.get(cid, 0) < _MIN_PER_CONDITION for cid in condition_ids):
        return {"ok": False, "reason": "insufficient data (need >=3 per condition)",
                "values": [],
                "descriptives": [{"condition": cond_names.get(cid, str(cid)), "n": counts.get(cid, 0)}
                                 for cid in condition_ids]}
    df = pd.DataFrame(rows).rename(columns={"condition_id": "condition"})
    paired = g["paired"]
    k = len(condition_ids)
    normal_tbl = pg.normality(df, dv="value", group="condition")
    normal = bool(normal_tbl["normal"].all())
    posthoc = []

    if k == 2:
        a = df[df.condition == condition_ids[0]]["value"]
        b = df[df.condition == condition_ids[1]]["value"]
        if paired:
            if normal:
                r = pg.ttest(a.values, b.values, paired=True); test = "paired t-test"
                stat, p = float(r["T"].iloc[0]), float(r["p_val"].iloc[0])
                eff = {"name": "cohen_d", "value": float(r["cohen_d"].iloc[0])}
            else:
                r = pg.wilcoxon(a.values, b.values); test = "Wilcoxon signed-rank"
                stat, p = float(r["W_val"].iloc[0]), float(r["p_val"].iloc[0])
                eff = {"name": "rank-biserial", "value": float(r["RBC"].iloc[0])}
        else:
            if normal:
                r = pg.ttest(a.values, b.values, paired=False); test = "independent t-test"
                stat, p = float(r["T"].iloc[0]), float(r["p_val"].iloc[0])
                eff = {"name": "cohen_d", "value": float(r["cohen_d"].iloc[0])}
            else:
                r = pg.mwu(a.values, b.values); test = "Mann-Whitney U"
                stat, p = float(r["U_val"].iloc[0]), float(r["p_val"].iloc[0])
                eff = {"name": "rank-biserial", "value": float(r["RBC"].iloc[0])}
    else:
        if paired:
            if normal:
                r = pg.rm_anova(data=df, dv="value", within="condition", subject="subject", detailed=True)
                row = r[r["Source"] == "condition"].iloc[0]
                test = "repeated-measures ANOVA"; stat, p = float(row["F"]), float(row["p_unc"])
                eff = {"name": "generalized eta^2", "value": float(row["ng2"])}
            else:
                r = pg.friedman(data=df, dv="value", within="condition", subject="subject")
                test = "Friedman"; stat, p = float(r["Q"].iloc[0]), float(r["p_unc"].iloc[0])
                eff = {"name": "Kendall W", "value": float(r["W"].iloc[0])}
        else:
            if normal:
                r = pg.anova(data=df, dv="value", between="condition", detailed=True)
                row = r[r["Source"] == "condition"].iloc[0]
                test = "one-way ANOVA"; stat, p = float(row["F"]), float(row["p_unc"])
                eff = {"name": "partial eta^2", "value": float(row["np2"])}
            else:
                r = pg.kruskal(data=df, dv="value", between="condition")
                test = "Kruskal-Wallis"; stat, p = float(r["H"].iloc[0]), float(r["p_unc"].iloc[0])
                n_total = len(df)
                eps2 = (stat - k + 1) / (n_total - k) if n_total > k else 0.0
                eff = {"name": "epsilon^2", "value": float(eps2)}
        if p < 0.05:
            kw = {"within": "condition", "subject": "subject"} if paired else {"between": "condition"}
            pt = pg.pairwise_tests(data=df, dv="value", padjust="holm", **kw)
            for _, prow in pt.iterrows():
                ac, bc = prow["A"], prow["B"]
                posthoc.append({"a": cond_names.get(ac, str(ac)), "b": cond_names.get(bc, str(bc)),
                                "p_corr": float(prow["p_corr"]), "sig": bool(prow["p_corr"] < 0.05)})

    eff["magnitude"] = _magnitude(eff["name"], eff["value"])
    descr = _descriptives(df, cond_names, normal_tbl)
    sig = p < 0.05
    posthoc_txt = ""
    if posthoc:
        pairs = [f"{x['a']} vs {x['b']} (p={x['p_corr']:.3f})" for x in posthoc if x["sig"]]
        posthoc_txt = " Post-hoc: " + (", ".join(pairs) if pairs else "no pair survived correction") + "."
    names = ", ".join(cond_names.get(cid, str(cid)) for cid in condition_ids)
    interp = (f"Comparing {names}. "
              f"{test} ({'data normal' if normal else 'non-normal'}; {g['paired'] and 'within-subjects' or 'between-subjects'}; "
              f"{k} conditions): statistic={stat:.3f}, p={p:.4f}, {eff['name']}={eff['value']:.3f} ({eff['magnitude']}). "
              f"{'Significant.' if sig else 'Not significant.'}{posthoc_txt}")
    return {"ok": True, "test": test, "design": "paired" if g["paired"] else "unpaired",
            "normal": normal, "statistic": stat, "p": p, "effect_size": eff,
            "descriptives": descr, "posthoc": posthoc,
            "values": [{"condition": cond_names.get(r["condition_id"], ""),
                        "subject": r["subject"], "value": r["value"]} for r in rows],
            "interpretation": interp}


def compare(db, experiment_id, condition_ids, signal, feature, unit, cond_names):
    g = gather(db, experiment_id, condition_ids, signal, feature, unit)
    res = run_test(g, condition_ids, cond_names)
    res["signal"] = signal
    res["feature"] = feature
    res["unit"] = unit
    return res
