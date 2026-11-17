"""ดึงข้อมูลลุ่มน้ำและอ่างเก็บน้ำสำหรับหน้าชลประทาน จากระบบสมดุลน้ำ กรมชลประทาน (ทดลอง) ทุก 6 ชม.

ต้นทางเป็นข้อมูลของคลังข้อมูลน้ำแห่งชาติ (ThaiWater) สสน. ที่ระบบสมดุลน้ำรวบรวมไว้ เซิร์ฟเวอร์นั้นไม่เปิด CORS
หน้าเว็บจึงอ่านตรงไม่ได้ ต้องดึงมาเก็บใน data/water ตอน build ย่อเหลือเฉพาะช่องที่หน้าเว็บใช้

  data/water/basins.json  22 ลุ่มน้ำหลัก: สถานะระดับน้ำในลำน้ำ (สถานีที่แย่ที่สุด), จำนวนสถานีแต่ละระดับ, ฝน 24 ชม., สถานีวัดระดับน้ำ
  data/water/dams.json    อ่างเก็บน้ำขนาดใหญ่: % ความจุ, ปริมาณน้ำ, น้ำไหลเข้า, น้ำระบาย

ถ้าดึงไม่ได้ เก็บไฟล์เดิมไว้ (workflow เก็บไฟล์ใน cache ข้ามรอบ)
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SRC = "https://survey.serveftp.net/waterbalance/data"
OUT = Path(__file__).resolve().parent / "data" / "water"


def get(path: str):
    req = urllib.request.Request(f"{SRC}/{path}", headers={"User-Agent": "rainmap-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def th(v):
    return v.get("th") if isinstance(v, dict) else v


def basins() -> dict:
    ov = get("forecast/overview.json")
    if ov.get("state") != "ok":
        raise RuntimeError("overview.json state = " + str(ov.get("state")))
    out = []
    for b in ov["basins"]:
        r = b.get("rain24") or {}
        out.append({
            "id": b["id"], "name": th(b["name"]).removeprefix("ลุ่มน้ำ"), "center": b.get("center"),
            "worst": b.get("worst"), "counts": b.get("counts"), "n": b.get("nStations"),
            "rain": {"mean": r.get("mean"), "max": r.get("max"), "maxAt": th(r.get("maxAt")), "n": r.get("n")},
            "stations": [{
                "name": th(s["name"]), "river": s.get("river"), "prov": th(s.get("province")),
                "lat": s["lat"], "lon": s["lon"], "level": s.get("level"), "pct": s.get("pct"),
                "wl": s.get("wl"), "bank": s.get("bank"), "toBankCm": s.get("toBankCm"), "time": s.get("time"),
            } for s in b.get("stations", []) if s.get("lat") is not None],
        })
    return {"made": ov.get("made"), "waterlevelTime": ov.get("waterlevelTime"), "rain24Time": ov.get("rain24Time"),
            "credit": th(ov.get("credit")), "basins": out}


def dams() -> dict:
    d = get("obs/thaiwater/dams.json")
    keep = ("storageMcm", "pct", "usablePct", "inflowMcm", "releasedMcm", "usableMcm", "maxMcm", "normalMcm", "date")
    items = [{"name": th(x["name"]), "lat": x["lat"], "lon": x["lon"], "basin": th(x.get("basin")), "prov": th(x.get("province")),
              "agency": th(x.get("agency")), **{k: x.get(k) for k in keep}}
             for x in d["items"] if x.get("lat") is not None]
    return {"fetched": d.get("fetched"), "items": items}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ok = True
    for name, fn in (("basins", basins), ("dams", dams)):
        try:
            data = fn()
            data["copied"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            print(name, "ok", (OUT / f"{name}.json").stat().st_size, "bytes")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(name, "ล้มเหลว:", e, "(ใช้ไฟล์เดิม)" if (OUT / f"{name}.json").exists() else "")
    return 0 if ok or "--soft" in sys.argv else 1


if __name__ == "__main__":
    sys.exit(main())
