"""Facial ROI boxes from dlib 68-landmarks + scaling to the thermal array.
Ported from hri_server.py RegionsOfInterest."""


class RegionsOfInterest:
    def __init__(self, coords_x, coords_y):
        self.x = coords_x
        self.y = coords_y
        self.eyes_dist = self.x[45] - self.x[36]
        self.regions = {
            "forehead": self._forehead(),
            "left_cheek": self._left_cheek(),
            "right_cheek": self._right_cheek(),
            "nose": self._nose(),
        }

    def _forehead(self):
        interm = self.x[23] - self.x[20]
        return [self.x[21], self.y[20] - interm / 2, self.x[22], self.y[23] - interm / 4]

    def _left_cheek(self):
        return [self.x[4], self.y[14], self.x[6], self.y[13]]

    def _right_cheek(self):
        return [self.x[10], self.y[14], self.x[12], self.y[13]]

    def _nose(self):
        return [self.x[32], self.y[29], self.x[34], self.y[30]]

    def get(self, names):
        return {n: self.regions[n] for n in names if n in self.regions}


def scale_roi_to_thermal(box, sx, sy, tw, th):
    """Scale a palette-space (x0,y0,x1,y1) box into thermal pixel coords, clamped."""
    x0, y0, x1, y1 = box
    tx0 = max(0, min(int(x0 * sx), tw - 1))
    ty0 = max(0, min(int(y0 * sy), th - 1))
    tx1 = max(0, min(int(x1 * sx), tw))
    ty1 = max(0, min(int(y1 * sy), th))
    return tx0, ty0, tx1, ty1
