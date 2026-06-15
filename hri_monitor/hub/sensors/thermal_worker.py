"""Standalone Optris-SDK + dlib subprocess. Writes length-prefixed frame+temps
messages to stdout. Ported from hri_server.py capture_loop(). Runs in its own
process so an SDK segfault cannot crash the hub."""
import argparse
import ctypes as ct
import ctypes.util  # noqa: F401 — populates ct.util for find_library() below
import sys
import time

import numpy as np

from hub.sensors.roi import RegionsOfInterest, scale_roi_to_thermal
from hub.sensors.thermal_codec import encode_message


class EvoIRFrameMetadata(ct.Structure):
    _fields_ = [
        ("counter", ct.c_uint), ("counterHW", ct.c_uint),
        ("timestamp", ct.c_longlong), ("timestampMedia", ct.c_longlong),
        ("flagState", ct.c_int), ("tempChip", ct.c_float),
        ("tempFlag", ct.c_float), ("tempBox", ct.c_float),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", required=True)
    ap.add_argument("--detector", required=True)
    ap.add_argument("--predictor", required=True)
    ap.add_argument("--format-dir", required=True)
    ap.add_argument("--out-fd", type=int, default=1,
                    help="fd to write framed messages to (default stdout). A "
                         "dedicated fd keeps the binary protocol clean from the "
                         "Optris SDK / library logging that pollutes stdout.")
    args = ap.parse_args()
    import os

    out = os.fdopen(args.out_fd, "wb")

    import cv2
    import dlib

    libir = ct.cdll.LoadLibrary(ct.util.find_library("irdirectsdk"))
    pw, ph, tw, th = ct.c_int(), ct.c_int(), ct.c_int(), ct.c_int()
    meta = EvoIRFrameMetadata()
    if libir.evo_irimager_usb_init(args.xml.encode(), args.format_dir.encode(), b"log") != 0:
        print("evo_irimager_usb_init failed", file=sys.stderr); sys.exit(2)
    libir.evo_irimager_get_thermal_image_size(ct.byref(tw), ct.byref(th))
    libir.evo_irimager_get_palette_image_size(ct.byref(pw), ct.byref(ph))
    np_thermal = np.zeros([tw.value * th.value], dtype=np.uint16)
    np_img = np.zeros([pw.value * ph.value * 3], dtype=np.uint8)
    p_th = np_thermal.ctypes.data_as(ct.POINTER(ct.c_ushort))
    p_im = np_img.ctypes.data_as(ct.POINTER(ct.c_ubyte))

    detector = dlib.simple_object_detector(args.detector)
    predictor = dlib.shape_predictor(args.predictor)
    last_detect = 0.0
    rect = None
    last_valid = {}

    while True:
        if libir.evo_irimager_get_thermal_palette_image_metadata(
                tw, th, p_th, pw, ph, p_im, ct.byref(meta)) != 0:
            continue
        thermal = np_thermal.reshape((th.value, tw.value)).astype(np.float32)
        tmap = thermal / 10.0 - 100.0
        palette = np_img.reshape((ph.value, pw.value, 3))
        display = palette[:, :, ::-1].copy()  # BGR for output + dlib
        now = time.time()
        if rect is None or now - last_detect > 5.0:
            dets = detector(cv2.cvtColor(display, cv2.COLOR_BGR2GRAY))
            rect = dets[0] if dets else None
            if rect is not None:
                last_detect = now
        temps = {}
        if rect is not None:
            shape = predictor(display, rect)
            xs = [p.x for p in shape.parts()]
            ys = [p.y for p in shape.parts()]
            # Draw all 68 facial landmarks (blue dots) — same as hri_server.py.
            for x, y in zip(xs, ys):
                cv2.circle(display, (x, y), 1, (255, 0, 0), 2)
            roi = RegionsOfInterest(xs, ys)
            sx, sy = tw.value / pw.value, th.value / ph.value
            for name, box in roi.get(["forehead", "left_cheek", "right_cheek", "nose"]).items():
                x0, y0, x1, y1 = map(int, box)
                cv2.rectangle(display, (x0, y0), (x1, y1), (0, 255, 0), 2)
                tx0, ty0, tx1, ty1 = scale_roi_to_thermal((x0, y0, x1, y1), sx, sy, tw.value, th.value)
                if tx1 > tx0 and ty1 > ty0:
                    avg = round(float(np.mean(tmap[ty0:ty1, tx0:tx1])), 2)
                    temps[name] = avg
                    cv2.putText(display, f"{avg:.1f}C", (x0, y0 - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        if temps and all(v is not None for v in temps.values()):
            last_valid = temps.copy()
        elif last_valid:
            temps = last_valid.copy()
        # Emit exactly as hri_server.py served its /thermal view: the reversed
        # palette with ROI overlays. Correct colours depend on the right
        # Formats.def (the usb_init format dir), not on the channel order.
        out.write(encode_message(temps, display))
        out.flush()
        time.sleep(0.03)


if __name__ == "__main__":
    main()
