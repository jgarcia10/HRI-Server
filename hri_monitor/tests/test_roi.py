from hub.sensors.roi import RegionsOfInterest, scale_roi_to_thermal


def test_regions_selects_named_boxes():
    xs = list(range(68))
    ys = list(range(68))
    roi = RegionsOfInterest(xs, ys)
    sel = roi.get(["forehead", "left_cheek", "right_cheek", "nose"])
    assert set(sel) == {"forehead", "left_cheek", "right_cheek", "nose"}
    for box in sel.values():
        assert len(box) == 4


def test_scale_roi_clamps_into_thermal_bounds():
    box = scale_roi_to_thermal((10, 20, 50, 60), sx=0.5, sy=0.5, tw=160, th=120)
    assert box == (5, 10, 25, 30)
    big = scale_roi_to_thermal((0, 0, 1000, 1000), sx=0.5, sy=0.5, tw=160, th=120)
    assert big[2] <= 160 and big[3] <= 120
