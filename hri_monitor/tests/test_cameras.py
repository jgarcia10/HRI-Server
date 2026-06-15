from hub.cameras import list_cameras_from_sysfs


def test_list_cameras_reads_names(tmp_path):
    for idx, name in [(0, "Integrated Cam"), (2, "USB Webcam")]:
        d = tmp_path / f"video{idx}"
        d.mkdir()
        (d / "name").write_text(name + "\n")
    cams = list_cameras_from_sysfs(str(tmp_path))
    assert {"index": 0, "path": "/dev/video0", "name": "Integrated Cam"} in cams
    assert {"index": 2, "path": "/dev/video2", "name": "USB Webcam"} in cams
    assert cams == sorted(cams, key=lambda c: c["index"])
