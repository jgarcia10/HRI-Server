"""Real USB RGB camera → MediaPipe blink/EAR. Heavy deps imported lazily in
connect() so the hub starts without cv2/mediapipe present."""
import time

import numpy as np

from .base import BaseSensor
from .blink_math import LEFT_EYE_IDX, RIGHT_EYE_IDX, BlinkRate, eye_aspect_ratio


class RealRGB(BaseSensor):
    name = "rgb"

    def __init__(self, bus, index=0, width=640, height=480, fps=30):
        super().__init__(bus)
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps
        self._cap = None
        self._mesh = None
        self._blink = None

    def connect(self):
        import cv2
        import mediapipe as mp

        self._cv2 = cv2
        cap = cv2.VideoCapture(self.index, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(f"cannot open camera /dev/video{self.index}")
        self._cap = cap
        self._mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1, refine_landmarks=True,
            min_detection_confidence=0.5, min_tracking_confidence=0.5)
        self._blink = BlinkRate()

    def read(self):
        cv2 = self._cv2
        ok, frame = self._cap.read()
        if not ok:
            raise RuntimeError("camera read failed")
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._mesh.process(rgb)
        t = time.time()
        ear = 0.0
        if results.multi_face_landmarks:
            h, w, _ = frame.shape
            lm = results.multi_face_landmarks[0]

            def pts(idx):
                return np.array([(lm.landmark[i].x * w, lm.landmark[i].y * h) for i in idx])

            left, right = pts(LEFT_EYE_IDX), pts(RIGHT_EYE_IDX)
            ear = (eye_aspect_ratio(left) + eye_aspect_ratio(right)) / 2.0
            for p in np.vstack([left, right]).astype(int):
                cv2.circle(frame, tuple(p), 2, (0, 255, 0), -1)
            cv2.putText(frame, f"EAR: {ear:.2f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        rate = self._blink.update(ear, t)
        cv2.putText(frame, f"Blink: {rate:.1f}/min", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        self.emit("rgb.frame", {"frame": frame})
        self.emit("rgb.blink", {"rate": round(max(rate, 0.0), 2), "ear": round(ear, 3)})
        time.sleep(0.01)

    def disconnect(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if self._mesh is not None:
            self._mesh.close()
            self._mesh = None
