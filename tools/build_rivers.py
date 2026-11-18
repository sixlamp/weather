"""สร้าง water_rivers.json: เส้นแม่น้ำสายหลักในไทยจาก OpenStreetMap (© OpenStreetMap contributors, ODbL)
ใช้ในหน้าชลประทาน รันครั้งเดียว (หรือเมื่ออยากปรับปรุงเส้น) แล้ว commit ไฟล์ผลลัพธ์

  python tools/build_rivers.py              ดึงจาก Overpass API แล้วสร้างไฟล์
  python tools/build_rivers.py raw.json     ใช้ไฟล์ที่ดึงไว้แล้ว (ผลของ Overpass แบบ out tags geom)

เลือกเฉพาะ waterway=river ที่มีชื่อ และความยาวรวมของชื่อนั้นตั้งแต่ MIN_KM ขึ้นไป
ต่อท่อนที่ปลายชนกันเป็นเส้นยาว ย่อจุดด้วย Douglas-Peucker แล้วปัดพิกัดเหลือ 3 ตำแหน่ง (~100 ม.)
"""
import json
import math
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "water_rivers.json"
MIN_KM = 50          # แม่น้ำสั้นกว่านี้ไม่เอา (ส่วนใหญ่เป็นลำน้ำสาขาเล็ก)
TOL = 0.004          # ความคลาดเคลื่อนที่ยอมได้ตอนย่อจุด (องศา ~400 ม.)
QUERY = '[out:json][timeout:240];area["ISO3166-1"="TH"][admin_level=2]->.th;way["waterway"="river"](area.th);out tags geom;'


def fetch() -> list:
    body = urllib.parse.urlencode({"data": QUERY}).encode()
    req = urllib.request.Request("https://overpass-api.de/api/interpreter", data=body, headers={"User-Agent": "weather-site-build/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))["elements"]


def km(line) -> float:
    return sum(math.hypot((b[0] - a[0]) * math.cos(math.radians(a[1])), b[1] - a[1]) * 111.2 for a, b in zip(line, line[1:]))


def chain(lines: list) -> list:
    """ต่อท่อนที่ปลายชนกัน (ใช้จุดปลายร่วมกัน) ให้เป็นเส้นยาวที่สุดเท่าที่ต่อได้"""
    lines = [list(l) for l in lines if len(l) >= 2]
    out = []
    while lines:
        cur = lines.pop()
        grown = True
        while grown:
            grown = False
            for i, l in enumerate(lines):
                if l[0] == cur[-1]: cur += l[1:]
                elif l[-1] == cur[-1]: cur += l[::-1][1:]
                elif l[-1] == cur[0]: cur = l[:-1] + cur
                elif l[0] == cur[0]: cur = l[::-1][:-1] + cur
                else: continue
                lines.pop(i); grown = True
                break
        out.append(cur)
    return out


def simplify(pts: list, tol: float) -> list:
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        n = math.hypot(dx, dy) or 1e-12
        best, at = 0.0, -1
        for i in range(a + 1, b):
            x, y = pts[i]
            d = abs(dy * (x - x1) - dx * (y - y1)) / n
            if d > best: best, at = d, i
        if best > tol:
            keep[at] = True
            stack += [(a, at), (at, b)]
    return [p for p, k in zip(pts, keep) if k]


def main():
    elems = json.load(open(sys.argv[1], encoding="utf-8"))["elements"] if len(sys.argv) > 1 else fetch()
    by = defaultdict(list)
    for w in elems:
        t = w.get("tags", {})
        name = t.get("name:th") or t.get("name")
        g = w.get("geometry")
        if name and g:
            by[name].append([(p["lon"], p["lat"]) for p in g])
    rivers = []
    for name, segs in by.items():
        total = sum(km(s) for s in segs)
        if total < MIN_KM:
            continue
        lines = []
        for l in chain(segs):
            s = [[round(x, 3), round(y, 3)] for x, y in simplify(l, TOL)]
            s = [p for i, p in enumerate(s) if i == 0 or p != s[i - 1]]
            if len(s) >= 2:
                lines.append(s)
        # ขนาดเส้น: 3 = สายหลักยาวมาก, 2 = สายใหญ่, 1 = สายรอง
        rivers.append({"n": name, "w": 3 if total >= 300 else 2 if total >= 120 else 1, "km": round(total), "l": lines})
    rivers.sort(key=lambda r: r["km"])     # สายยาวไว้ท้าย วาดทีหลังจึงอยู่ด้านบน
    doc = {"made": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "source": "© OpenStreetMap contributors (ODbL), waterway=river ที่มีชื่อ ยาวรวม >= %d กม." % MIN_KM, "rivers": rivers}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    pts = sum(len(l) for r in rivers for l in r["l"])
    print(f"{len(rivers)} rivers, {sum(len(r['l']) for r in rivers)} lines, {pts} points, {OUT.stat().st_size // 1024} KB -> {OUT.name}")


if __name__ == "__main__":
    main()
