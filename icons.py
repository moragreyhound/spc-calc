"""Line icons drawn with PIL — no emoji, no external assets.

Every icon is a 24x24 stroke icon rendered at 4x and downsampled, so it
stays crisp on high-DPI displays. Colors come from the active theme.
"""

from __future__ import annotations

import customtkinter as ctk
from PIL import Image, ImageDraw

_SUPERSAMPLE = 4
_CACHE: dict[tuple[str, str, int], ctk.CTkImage] = {}


def get(name: str, color: str, size: int = 18) -> ctk.CTkImage:
    key = (name, color, size)
    if key not in _CACHE:
        _CACHE[key] = _draw(name, color, size)
    return _CACHE[key]


def _draw(name: str, color: str, size: int) -> ctk.CTkImage:
    s = _SUPERSAMPLE
    dim = 24 * s
    image = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    w = 2 * s  # stroke width

    def line(points):
        xy = [(x * s, y * s) for x, y in points]
        draw.line(xy, fill=color, width=w, joint="curve")

    def rect(x0, y0, x1, y1):
        draw.rectangle([x0 * s, y0 * s, x1 * s, y1 * s], outline=color, width=w)

    def arc(cx, cy, r, start, end):
        bbox = [(cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s]
        draw.arc(bbox, start, end, fill=color, width=w)

    def circle(cx, cy, r):
        bbox = [(cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s]
        draw.ellipse(bbox, outline=color, width=w)

    def dot(cx, cy, r):
        bbox = [(cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s]
        draw.ellipse(bbox, fill=color)

    if name == "file":
        line([(6, 4), (13, 4)])
        line([(13, 4), (13, 8)])
        line([(13, 8), (17, 8)])
        line([(17, 8), (17, 20)])
        line([(17, 20), (6, 20)])
        line([(6, 20), (6, 4)])
    elif name == "text":
        line([(6, 4), (13, 4), (13, 8), (17, 8), (17, 20), (6, 20), (6, 4)])
        line([(13, 4), (13, 8), (17, 8)])
        line([(9, 12.5), (15, 12.5)])
        line([(9, 15.5), (15, 15.5)])
        line([(9, 18.5), (12.5, 18.5)])
    elif name == "image":
        rect(4, 5, 20, 19)
        circle(9, 10, 2)
        line([(6, 17), (11, 12), (14, 15.5), (16, 13.5), (19, 17)])
    elif name == "audio":
        line([(4, 10), (7, 10), (11, 6), (11, 18), (7, 14), (4, 14)])
        line([(4, 10), (4, 14)])
        line([(14, 9.5), (14, 14.5)])
        line([(16.5, 7.5), (16.5, 16.5)])
        line([(19, 5.5), (19, 18.5)])
    elif name == "video":
        rect(3, 6, 21, 18)
        line([(10.5, 9.5), (10.5, 14.5), (15, 12), (10.5, 9.5)])
    elif name == "code":
        line([(8.5, 8), (5, 12), (8.5, 16)])
        line([(15.5, 8), (19, 12), (15.5, 16)])
        line([(13.5, 6.5), (10.5, 17.5)])
    elif name == "pdf":
        line([(6, 4), (13, 4), (13, 8), (17, 8), (17, 20), (6, 20), (6, 4)])
        line([(13, 4), (13, 8), (17, 8)])
        line([(9, 13), (15, 13)])
        line([(9, 16), (13.5, 16)])
    elif name == "archive":
        rect(4, 4, 20, 20)
        line([(4, 9), (20, 9)])
        dot(8, 6.5, 0.7)
        dot(12, 6.5, 0.7)
        dot(16, 6.5, 0.7)
        line([(12, 9), (12, 14)])
        dot(12, 15.5, 0.7)
    elif name == "lock":
        rect(6, 10.5, 18, 20)
        arc(12, 10.5, 3.5, 180, 360)
        circle(12, 14.5, 1.3)
        line([(12, 15.8), (12, 17.5)])
    elif name == "unlock":
        rect(6, 10.5, 18, 20)
        arc(12, 10.5, 3.5, 180, 300)
        circle(12, 14.5, 1.3)
        line([(12, 15.8), (12, 17.5)])
    elif name == "key":
        circle(7.5, 7.5, 3.5)
        line([(10.2, 10.2), (18, 18)])
        line([(14.5, 14.5), (16.5, 12.5)])
        line([(16.5, 16.5), (18.5, 14.5)])
    elif name == "upload":
        line([(12, 4), (12, 11)])
        line([(8.5, 7.5), (12, 4), (15.5, 7.5)])
        line([(4, 10), (4, 14), (20, 14), (20, 10)])
    elif name == "download":
        line([(12, 17.5), (12, 10.5)])
        line([(8.5, 13), (12, 17.5), (15.5, 13)])
        line([(4, 10), (4, 14), (20, 14), (20, 10)])
    elif name == "copy":
        rect(4, 9, 14, 19)
        rect(10, 4, 20, 14)
    elif name == "trash":
        line([(7, 7), (17, 7)])
        line([(10, 4.5), (14, 4.5)])
        line([(6, 7), (6.5, 19), (17.5, 19), (18, 7)])
        line([(10, 10.5), (10, 16)])
        line([(13, 10.5), (13, 16)])
        line([(16, 10.5), (16, 16)])
    elif name == "plus":
        line([(12, 5), (12, 19)])
        line([(5, 12), (19, 12)])
    elif name == "play":
        line([(9, 6.5), (9, 17.5), (17, 12), (9, 6.5)])
    elif name == "pause":
        line([(8.5, 6.5), (8.5, 17.5)])
        line([(15.5, 6.5), (15.5, 17.5)])
    elif name == "stop":
        rect(8, 8, 16, 16)
    elif name == "shield":
        line([(12, 3.5), (19, 6.5), (19, 12), (12, 20.5), (5, 12), (5, 6.5), (12, 3.5)])
        rect(9.5, 10.5, 14.5, 15)
        arc(12, 10.5, 2, 180, 360)
    elif name == "clock":
        circle(12, 12, 8)
        line([(12, 12), (12, 7)])
        line([(12, 12), (15.5, 13.5)])
    elif name == "warning":
        line([(12, 4.5), (20.5, 19.5), (3.5, 19.5), (12, 4.5)])
        line([(12, 9), (12, 14)])
        dot(12, 16.4, 0.5)
    elif name == "folder":
        line([(3, 6.5), (10, 6.5), (12, 4.5), (21, 4.5), (21, 19), (3, 19), (3, 6.5)])
    elif name == "chevron":
        line([(9, 7), (5, 12), (9, 17)])
    else:
        rect(5, 5, 19, 19)

    image = image.resize((size, size), Image.LANCZOS)
    return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))
