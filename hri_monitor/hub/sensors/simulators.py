"""Hardware-free sensor twins. They emit the same topics and payload shapes
as the real drivers (milestone 2), so the whole pipeline runs with no devices."""
import math
import random
import time

import cv2
import numpy as np

from .base import BaseSensor


class SimulatedShimmer(BaseSensor):
    name = "shimmer"

    def connect(self):
        pass

    def read(self):
        t = time.time()
        gsr = 4.0 + 0.8 * math.sin(t / 13.0) + random.gauss(0, 0.05)
        ppg = 1500.0 + 400.0 * math.sin(2 * math.pi * 1.2 * t) + random.gauss(0, 20.0)
        self.emit("shimmer.gsr", {"value": round(gsr, 3)})
        self.emit("shimmer.ppg", {"value": round(ppg, 1)})
        time.sleep(0.04)


class SimulatedThermal(BaseSensor):
    name = "thermal"

    ROIS = {
        "forehead": (130, 50, 190, 80),
        "left_cheek": (115, 120, 145, 150),
        "right_cheek": (175, 120, 205, 150),
        "nose": (150, 110, 170, 135),
    }
    BASE_TEMPS = {"forehead": 34.5, "left_cheek": 33.8, "right_cheek": 33.9, "nose": 32.5}

    def connect(self):
        pass

    def read(self):
        t = time.time()
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:] = (60, 30, 20)
        cv2.ellipse(frame, (160, 120), (70, 90), 0, 0, 360, (40, 60, 200), -1)
        temps = {}
        for roi, (x0, y0, x1, y1) in self.ROIS.items():
            temp = self.BASE_TEMPS[roi] + 0.4 * math.sin(t / 30.0) + random.gauss(0, 0.05)
            temps[roi] = round(temp, 2)
            cv2.rectangle(frame, (x0, y0), (x1, y1), (80, 255, 80), 1)
            cv2.putText(frame, f"{temps[roi]:.1f}", (x0, y0 - 3),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
        self.emit("thermal.frame", {"frame": frame})
        self.emit("thermal.temps", temps)
        time.sleep(0.1)


class SimulatedRGB(BaseSensor):
    name = "rgb"

    def connect(self):
        pass

    def read(self):
        t = time.time()
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:] = (30, 30, 30)
        cv2.circle(frame, (int(160 + 80 * math.sin(t)), 120), 30, (200, 180, 60), -1)
        cv2.putText(frame, "simulated rgb", (10, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        rate = 17.0 + 3.0 * math.sin(t / 20.0) + random.gauss(0, 0.3)
        self.emit("rgb.frame", {"frame": frame})
        self.emit("rgb.blink", {"rate": round(max(rate, 0.0), 2),
                                "ear": round(0.3 + random.gauss(0, 0.01), 3)})
        time.sleep(0.1)
