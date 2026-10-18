#!/usr/bin/env python3
"""
Draw Shishya's icon: शि on the panel's near-black, with the accent rule
under it — the mark from the panel's header, at every size Windows asks for.

    python windows/make_icon.py windows/shishya.ico

The glyph is drawn by Qt, not Pillow. शि is श followed by the vowel sign ि,
which is typed after the consonant but written BEFORE it, on its left. Getting
that right is text shaping (HarfBuzz, in Qt); Pillow without libraqm draws
the characters in typed order and puts the hook on the wrong side — which is
exactly what the first version of this icon did.
"""

import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QImage, QPainter

INK, PAPER, ACCENT = QColor(11, 12, 14), QColor(233, 235, 238), QColor(0, 120, 212)
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
GLYPH = "शि"                     # श + ि  →  शि
FACES = ("Nirmala UI", "Mangal", "Kohinoor Devanagari", "Noto Sans Devanagari")


def face():
    have = set(QFontDatabase.families())
    for name in FACES:
        if name in have:
            return name
    sys.exit("no Devanagari font on this machine — cannot draw शि correctly")


def draw(big=512):
    img = QImage(big, big, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(INK)
    p.drawRoundedRect(QRectF(0, 0, big, big), big / 9, big / 9)
    font = QFont(face())
    font.setPixelSize(int(big * 0.42))
    p.setFont(font)
    p.setPen(PAPER)
    # Centred on the ink the glyph actually covers, not on its line box, so
    # the hook of the matra above does not push the letter off centre.
    box = p.boundingRect(QRectF(0, 0, big, big), Qt.AlignCenter, GLYPH)
    p.drawText(QRectF(0, -big * 0.05, big, big), Qt.AlignCenter, GLYPH)
    p.fillRect(QRectF(big * 0.22, big * 0.80, big * 0.56, big * 0.04), ACCENT)
    p.end()
    del box
    return img


def to_pil(qimg):
    qimg = qimg.convertToFormat(QImage.Format_RGBA8888)
    return Image.frombuffer("RGBA", (qimg.width(), qimg.height()),
                            bytes(qimg.constBits()), "raw", "RGBA", 0, 1)


def main(out):
    # The native platform: it draws into an image without showing anything,
    # and unlike "offscreen" it sees the system's fonts.
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])   # noqa: F841
    master = to_pil(draw())
    images = [master.resize((s, s), Image.LANCZOS) for s in SIZES]
    images[-1].save(out, format="ICO", sizes=[(s, s) for s in SIZES], append_images=images[:-1])
    images[-1].save(Path(out).with_suffix(".png"))
    print(f"wrote {out} with {face()}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).with_name("shishya.ico")))
