"""สร้างไอคอนเว็บ (เมฆ + หยดฝน บนพื้นสีฟ้า) รันครั้งเดียว ผลลัพธ์ commit ไว้ใน repo  ใช้: python tools/build_icon.py (ต้องมี Pillow)

  icon-512.png, icon-192.png  ไอคอนตอนเพิ่มลงหน้าโฮม (manifest.json)
  apple-touch-icon.png        180 px สำหรับ iPhone
  favicon.png                 64 px ไอคอนบนแท็บ
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent
S = 2048                                   # วาดใหญ่ 4 เท่าแล้วย่อ ขอบจะเรียบ


def draw(full_bleed: bool) -> Image.Image:
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    top, bot = (59, 130, 246), (29, 78, 216)   # ไล่สีฟ้าจากบนลงล่าง
    bg = Image.new("RGBA", (S, S))
    for y in range(S):
        t = y / (S - 1)
        ImageDraw.Draw(bg).line([(0, y), (S, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bot)) + (255,))
    mask = Image.new("L", (S, S), 0)
    if full_bleed:
        mask.paste(255, (0, 0, S, S))          # apple-touch / maskable: เต็มกรอบ ระบบตัดมุมเอง
    else:
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.22), fill=255)
    im.paste(bg, (0, 0), mask)
    # เมฆ: วงกลม 3 วง + ฐานโค้ง
    w = (255, 255, 255, 255)
    u = S / 100
    d.ellipse((22 * u, 34 * u, 50 * u, 62 * u), fill=w)
    d.ellipse((36 * u, 20 * u, 70 * u, 54 * u), fill=w)
    d.ellipse((56 * u, 32 * u, 82 * u, 58 * u), fill=w)
    d.rounded_rectangle((22 * u, 44 * u, 82 * u, 62 * u), radius=9 * u, fill=w)
    # หยดฝน 3 หยด (วงกลม + สามเหลี่ยมปลายแหลมด้านบน)
    drop = (191, 219, 254, 255)
    for cx, cy in ((36, 76), (52, 82), (68, 76)):
        r = 5 * u
        x, y = cx * u, cy * u
        d.ellipse((x - r, y - r, x + r, y + r), fill=drop)
        d.polygon([(x - r * 0.92, y - r * 0.4), (x + r * 0.92, y - r * 0.4), (x, y - r * 2.3)], fill=drop)
    return im


def main():
    rounded, full = draw(False), draw(True)
    for name, img, px in (("icon-512.png", full, 512), ("icon-192.png", full, 192),
                          ("apple-touch-icon.png", full, 180), ("favicon.png", rounded, 64)):
        img.resize((px, px), Image.LANCZOS).save(OUT / name, optimize=True)
        print(name, (OUT / name).stat().st_size, "bytes")


if __name__ == "__main__":
    main()
