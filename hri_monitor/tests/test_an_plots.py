from hub.analysis.plots import figure_bytes


def sample():
    return [{"condition": "A", "subject": 1, "value": 2.0},
            {"condition": "A", "subject": 2, "value": 3.0},
            {"condition": "A", "subject": 3, "value": 2.5},
            {"condition": "B", "subject": 1, "value": 4.0},
            {"condition": "B", "subject": 2, "value": 5.0},
            {"condition": "B", "subject": 3, "value": 4.5}]


def test_svg_bytes():
    b = figure_bytes(sample(), ["A", "B"], "Mean GSR by condition", "GSR (µS)", "svg")
    assert b[:5] == b"<?xml" or b"<svg" in b[:200]


def test_pdf_bytes():
    b = figure_bytes(sample(), ["A", "B"], "Mean GSR by condition", "GSR (µS)", "pdf")
    assert b[:4] == b"%PDF"


def test_empty_values_still_renders():
    b = figure_bytes([], ["A", "B"], "t", "y", "svg")
    assert len(b) > 0
