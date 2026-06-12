from hub.config import load_config


def test_defaults_when_file_missing(tmp_path):
    cfg = load_config(tmp_path / "nope.yaml")
    assert cfg["server"]["port"] == 8000
    assert cfg["sensors"]["shimmer"]["simulate"] is True


def test_user_values_override_defaults_and_keep_the_rest(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("server:\n  port: 9001\n")
    cfg = load_config(p)
    assert cfg["server"]["port"] == 9001
    assert cfg["server"]["host"] == "127.0.0.1"
