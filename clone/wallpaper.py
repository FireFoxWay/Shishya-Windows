#!/usr/bin/env python3
"""
The live wallpapers, painted with QPainter instead of Cairo.

The shapes and the numbers come from vm/shell/galaxy.py and matrix.py
unchanged — build() and the colour ramp are imported, not copied — so the
galaxy on the Windows clone is the same galaxy as on the Mac. Only draw()
is new, because Cairo is not here.
"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QRadialGradient

import galaxy as _galaxy
import matrix as _matrix


class Galaxy(_galaxy.Galaxy):
    def draw(self, p, width, height):
        p.fillRect(0, 0, width, height, QColor.fromRgbF(0.016, 0.020, 0.035))
        cx, cy = width * 0.5, height * 0.52
        scale = min(width, height) / (_galaxy.RADIUS * 1.35)
        cos_a, sin_a = math.cos(self.angle), math.sin(self.angle)
        cos_t, sin_t = math.cos(self.tilt), math.sin(self.tilt)

        star = QColor.fromRgbF(1, 1, 1, 0.42)
        for x, y, z in self.stars:
            sx = x * cos_a - z * sin_a
            sz = x * sin_a + z * cos_a
            px = cx + sx * scale * 0.32
            py = cy + (y * cos_t - sz * sin_t) * scale * 0.32
            if 0 <= px < width and 0 <= py < height:
                p.fillRect(QRectF(px, py, 1, 1), star)

        buckets = {}
        for x, y, z, colour in self.points:
            sx = x * cos_a - z * sin_a
            sz = x * sin_a + z * cos_a
            px = cx + sx * scale
            py = cy + (y * cos_t - sz * sin_t) * scale
            if 0 <= px < width and 0 <= py < height:
                key = (round(colour[0], 1), round(colour[1], 1), round(colour[2], 1))
                buckets.setdefault(key, []).append((px, py, sz))
        for (r, g, b), pts in buckets.items():
            c = QColor.fromRgbF(r, g, b, 0.95)
            for px, py, sz in pts:
                size = 2.1 if sz > 0 else 1.5
                p.fillRect(QRectF(px, py, size, size), c)

        glow = QRadialGradient(QPointF(cx, cy), scale * 3.0)
        glow.setColorAt(0.0, QColor.fromRgbF(1.0, 0.96, 0.85, 0.55))
        glow.setColorAt(0.45, QColor.fromRgbF(1.0, 0.75, 0.45, 0.16))
        glow.setColorAt(1.0, QColor.fromRgbF(1.0, 0.6, 0.3, 0.0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(cx, cy), scale * 3.0, scale * 3.0)


class Matrix(_matrix.Matrix):
    def draw(self, p, width, height):
        if width != self.width or height != self.height or not self.columns:
            self._build(width, height)
        p.fillRect(0, 0, width, height, QColor.fromRgbF(0.008, 0.028, 0.012))
        p.setFont(QFont("Consolas", _matrix.COLUMN_W - 6))
        cw = _matrix.COLUMN_W
        for i, col in enumerate(self.columns):
            x = i * cw + 3
            head = col["head"]
            for t in range(_matrix.TRAIL):
                row = int(head) - t
                if row < 0 or row * cw > height:
                    continue
                if t == 0:
                    p.setPen(QColor.fromRgbF(0.82, 1.0, 0.86))
                else:
                    fade = (1 - t / _matrix.TRAIL) ** 1.6
                    p.setPen(QColor.fromRgbF(0.18, 0.95, 0.35, fade * 0.9))
                p.drawText(QPointF(x, row * cw + cw), col["chars"][t])


LIVE = {"galaxy": (Galaxy, _galaxy.FPS), "matrix": (Matrix, _matrix.FPS)}
