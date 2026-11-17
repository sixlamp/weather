"""สร้างภาพขอบเขต 22 ลุ่มน้ำหลัก (ตามรหัสลุ่มน้ำของ ThaiWater) สำหรับหน้าชลประทาน รันครั้งเดียว ผลลัพธ์ commit ไว้ใน repo

ไฟล์ overview.json ของระบบสมดุลน้ำไม่มีเส้นขอบลุ่มน้ำ จึงทำแบบเดียวกับหน้าเว็บของระบบนั้น (js/logic/basinmap.js):
ลุ่มน้ำย่อย HydroBASINS ระดับ 7 แต่ละหน่วยเป็นของลุ่มน้ำที่สถานีวัดฝนส่วนใหญ่ในหน่วยนั้นสังกัด (เสมอกัน: รหัสน้อยกว่า)
หน่วยที่ไม่มีสถานีและช่องว่างระหว่างหน่วย ภายในประเทศไทย ใช้ลุ่มน้ำของช่องข้าง ๆ (ขยายออกทีละช่อง)

ผลลัพธ์:
  water_basins.png   ภาพเทา 1 ช่องต่อ 0.01 องศา ค่าพิกเซล = รหัสลุ่มน้ำ (0 = นอกประเทศไทย) แถวบนสุด = ละติจูดเหนือสุด
  water_basins.json  กรอบภาพ {w, s, e, n, d}

ใช้: python tools/build_basins.py   (ต้องมี Pillow และต่อเน็ตได้)
"""
import json
import urllib.request
from collections import Counter, deque
from pathlib import Path

from PIL import Image, ImageDraw

SRC = "https://survey.serveftp.net/waterbalance/data"
G = {"w": 97.0, "s": 5.4, "e": 106.0, "n": 20.6, "d": 0.01}
OUT = Path(__file__).resolve().parent.parent


def get(path: str):
    req = urllib.request.Request(f"{SRC}/{path}", headers={"User-Agent": "rainmap-build/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def polys(geom):
    t = geom["type"]
    if t == "GeometryCollection":
        return [p for g in geom["geometries"] for p in polys(g)]
    c = geom["coordinates"]
    return [c] if t == "Polygon" else c if t == "MultiPolygon" else []


def main():
    W = round((G["e"] - G["w"]) / G["d"])
    H = round((G["n"] - G["s"]) / G["d"])
    px = lambda lon, lat: ((lon - G["w"]) / G["d"], (G["n"] - lat) / G["d"])

    units = get("ee/basins_l7.geojson")["features"]
    thai = get("ee/dem/thailand.geojson")
    gauges = [g for g in get("obs/thaiwater/rain24.json")["items"] if g.get("lat") is not None and g.get("basinId")]
    known = {b["id"] for b in get("forecast/overview.json")["basins"]}

    # หน่วยลุ่มย่อย -> ภาพรหัส (หน่วยที่ i ใช้ค่า i + 1, 0 = ไม่มี)
    ids = Image.new("I", (W, H), 0)
    d = ImageDraw.Draw(ids)
    for i, f in enumerate(units):
        for poly in polys(f["geometry"]):
            d.polygon([px(*p) for p in poly[0]], fill=i + 1)
            for hole in poly[1:]:
                d.polygon([px(*p) for p in hole], fill=0)
    mask = Image.new("L", (W, H), 0)
    dm = ImageDraw.Draw(mask)
    geom = thai["geometry"] if thai.get("type") == "Feature" else thai
    for poly in polys(geom):
        dm.polygon([px(*p) for p in poly[0]], fill=255)
        for hole in poly[1:]:
            dm.polygon([px(*p) for p in hole], fill=0)
    ida, ma = ids.load(), mask.load()

    votes = {}
    for g in gauges:
        x, y = px(g["lon"], g["lat"])
        x, y = int(x), int(y)
        if not (0 <= x < W and 0 <= y < H) or g["basinId"] not in known:
            continue
        u = ida[x, y]
        if u:
            votes.setdefault(u, Counter())[g["basinId"]] += 1
    unit_basin = {u: sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] for u, c in votes.items()}

    out = bytearray(W * H)
    q = deque()
    for y in range(H):
        for x in range(W):
            if ma[x, y] and ida[x, y] in unit_basin:
                out[y * W + x] = unit_basin[ida[x, y]]
                q.append(y * W + x)
    while q:
        k = q.popleft()
        x, y = k % W, k // W
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < W and 0 <= ny < H and ma[nx, ny] and not out[ny * W + nx]:
                out[ny * W + nx] = out[k]
                q.append(ny * W + nx)

    Image.frombytes("L", (W, H), bytes(out)).save(OUT / "water_basins.png", optimize=True)
    (OUT / "water_basins.json").write_text(json.dumps(G), encoding="utf-8")
    have = Counter(out)
    print(f"{W}x{H}", "basins:", sorted(b for b in have if b), "missing:", sorted(known - set(have)))


if __name__ == "__main__":
    main()
