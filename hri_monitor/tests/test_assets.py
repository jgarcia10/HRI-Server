import os

from hub.assets import resolve_asset


def test_resolve_absolute_existing(tmp_path):
    f = tmp_path / "x.xml"
    f.write_text("ok")
    assert resolve_asset(str(f)) == str(f)


def test_resolve_absolute_missing_returns_none():
    assert resolve_asset("/nonexistent/nope.xml") is None


def test_resolve_relative_against_cwd(tmp_path, monkeypatch):
    (tmp_path / "cal.xml").write_text("ok")
    monkeypatch.chdir(tmp_path)
    got = resolve_asset("cal.xml")
    assert got is not None and got.endswith("cal.xml") and os.path.isabs(got)


def test_resolve_none_or_empty():
    assert resolve_asset(None) is None
    assert resolve_asset("") is None
