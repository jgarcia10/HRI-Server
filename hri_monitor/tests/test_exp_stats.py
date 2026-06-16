import math

from hub.experiments.stats import summarize_csv


def test_summarize_basic_stats(tmp_path):
    p = tmp_path / "rec.csv"
    p.write_text(
        "t_offset,signal,value\n"
        "0.0,shimmer.gsr,2.0\n"
        "0.1,shimmer.gsr,4.0\n"
        "0.2,shimmer.gsr,6.0\n"
        "0.0,thermal.forehead,34.0\n"
        "0.1,thermal.forehead,36.0\n"
    )
    s = summarize_csv(p)
    assert s["shimmer.gsr"]["count"] == 3
    assert s["shimmer.gsr"]["mean"] == 4.0
    assert s["shimmer.gsr"]["min"] == 2.0
    assert s["shimmer.gsr"]["max"] == 6.0
    # population std of [2,4,6] = sqrt(8/3) ≈ 1.633
    assert math.isclose(s["shimmer.gsr"]["std"], math.sqrt(8 / 3), rel_tol=1e-6)
    assert s["thermal.forehead"]["count"] == 2
    assert s["thermal.forehead"]["mean"] == 35.0


def test_summarize_single_value_has_zero_std(tmp_path):
    p = tmp_path / "rec.csv"
    p.write_text("t_offset,signal,value\n0.0,ppg.hr,72.0\n")
    s = summarize_csv(p)
    assert s["ppg.hr"]["count"] == 1
    assert s["ppg.hr"]["std"] == 0.0
    assert s["ppg.hr"]["mean"] == 72.0


def test_summarize_empty_or_header_only(tmp_path):
    p = tmp_path / "rec.csv"
    p.write_text("t_offset,signal,value\n")
    assert summarize_csv(p) == {}


def test_summarize_missing_file_returns_empty(tmp_path):
    assert summarize_csv(tmp_path / "nope.csv") == {}


def test_summarize_skips_malformed_rows(tmp_path):
    p = tmp_path / "rec.csv"
    p.write_text(
        "t_offset,signal,value\n"
        "0.0,shimmer.gsr,3.0\n"
        "0.1,shimmer.gsr,notanumber\n"   # bad value — skipped
        "0.2,shimmer.gsr,5.0\n"
    )
    s = summarize_csv(p)
    assert s["shimmer.gsr"]["count"] == 2
    assert s["shimmer.gsr"]["mean"] == 4.0
