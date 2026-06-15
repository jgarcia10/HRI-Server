from hub.config import DEFAULTS, load_config, save_config


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


def test_defaults_have_real_device_keys():
    s = DEFAULTS["sensors"]
    assert s["rgb"]["index"] == 0 and s["rgb"]["fps"] == 30
    assert s["thermal"]["detector"].endswith(".svm")
    assert s["thermal"]["predictor"].endswith(".dat")
    assert "format_dir" in s["thermal"]
    assert s["shimmer"]["mac"] is None and s["shimmer"]["sampling_rate"] == 200


def test_save_config_roundtrips(tmp_path):
    p = tmp_path / "config.yaml"
    cfg = load_config(p)
    cfg["sensors"]["rgb"]["index"] = 4
    cfg["sensors"]["rgb"]["simulate"] = False
    save_config(p, cfg)
    reloaded = load_config(p)
    assert reloaded["sensors"]["rgb"]["index"] == 4
    assert reloaded["sensors"]["rgb"]["simulate"] is False
