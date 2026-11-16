"""ดึงพยากรณ์ 7 วัน ทุก 3 ชม. จาก GFS 0.25 องศา ผ่าน NOAA NOMADS (grib filter ตัดเฉพาะภูมิภาค)

  data/forecast/rain.bin   uint8 [ช่วง 56 ช่วง ช่วงละ 3 ชม.][แถว ใต้ไปเหนือ][คอลัมน์ ตะวันตกไปตะวันออก] ฝนในช่วงนั้น
                           v <= 200: v / 10 มม., มากกว่านั้น: 20 + (v - 200) * 2 มม., 255 = ไม่มีข้อมูล
  data/forecast/meta.json
  data/forecast/wind.bin   int8 [เวลา 57 จุด ห่างกัน 3 ชม.][u แล้ว v][แถว][คอลัมน์] ค่า x 0.5 = ม./วินาที กริด 0.5 องศา
  data/forecast/pres.bin   uint16 [เวลา][แถว][คอลัมน์] ค่า + 85000 = Pa
  data/forecast/wnow.bin   int8 [ชั่วโมง 0..NOW_HOURS นับจาก init][u แล้ว v][แถว][คอลัมน์] ลม 10 ม. รายชั่วโมง (หน้าอากาศตอนนี้)
  data/forecast/tnow.bin   uint8 [ชั่วโมง 0..NOW_HOURS นับจาก init][แถว][คอลัมน์] อุณหภูมิ 2 ม. รายชั่วโมง ถอดค่าเหมือน temp.bin
  data/forecast/temp.bin   uint8 [วันตามปฏิทินไทย 7 วัน][ต่ำสุด แล้ว สูงสุด][แถว][คอลัมน์] ค่า / 2 - 40 = องศาเซลเซียส 255 = ไม่มีข้อมูล

ฝนช่วงที่ k = ฝนสะสมถึง f(3k+3) ลบ ฝนสะสมถึง f(3k) (GFS เก็บสะสมเป็นช่วง ใช้ช่วงไหนก็ต่อกันเป็นค่าสะสมจากชั่วโมง 0)
ลมและความกดอากาศเป็นค่า ณ เวลา f(3t)
อุณหภูมิ 2 ม.: ต่ำสุด = ค่าน้อยสุดของ TMIN ทุกช่วงที่จบ 04:00-10:00 น. สูงสุด = ค่ามากสุดของ TMAX ทุกช่วงที่จบ 13:00-19:00 น.
ของวันที่ k ตามปฏิทินไทย (วัน k = วันที่ของ init + 7 ชม. + k วัน) ถ้าช่วงนั้นผ่านไปแล้ว ณ เวลา init จะไม่มีข้อมูล
"""
import json
import struct
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import grib2

OUT = Path(__file__).resolve().parent / "data" / "forecast"
FILTER = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
# กรอบภูมิภาค: พม่า ลาว เวียดนาม กัมพูชา มาเลเซีย สิงคโปร์ จีนตอนใต้ อินโดนีเซียตอนบน
WEST, EAST, SOUTH, NORTH = 90, 115, -5, 28
DAYS = 7
STEP_H = 3           # ฝน/ลม/ความกดอากาศ ทุก 3 ชม. (GFS มีทุก 3 ชม. หรือถี่กว่าตลอด 7 วัน)
HOURS = DAYS * 24
NSTEPS = HOURS // STEP_H
MIN_END = {4, 7, 10}    # ชั่วโมงไทยที่ช่วง TMIN จบ ที่นับเป็นค่าต่ำสุดตอนเช้า
MAX_END = {13, 16, 19}  # ชั่วโมงไทยที่ช่วง TMAX จบ ที่นับเป็นค่าสูงสุดตอนบ่าย
SCALE = 0.1
NODATA = 65535
TIMEOUT = 60
NOW_HOURS = 30       # อุณหภูมิรายชั่วโมง f000..f030 พอครอบช่วงที่หน้าเว็บเปิดดูก่อนรอบถัดไปมา
WX_STEP = 2          # ลม/ความกดอากาศ เก็บทุก 2 จุด = 0.5 องศา
PAUSE = 0.4          # เว้นจังหวะระหว่างคำขอ ไม่ให้ถี่เกินไปกับ NOMADS


def _url(cycle: datetime, fh: int) -> str:
    ymd, hh = cycle.strftime("%Y%m%d"), cycle.strftime("%H")
    return (f"{FILTER}?dir=%2Fgfs.{ymd}%2F{hh}%2Fatmos&file=gfs.t{hh}z.pgrb2.0p25.f{fh:03d}"
            f"&var_APCP=on&var_UGRD=on&var_VGRD=on&var_PRMSL=on&var_TMIN=on&var_TMAX=on&var_TMP=on"
            f"&lev_surface=on&lev_10_m_above_ground=on&lev_2_m_above_ground=on&lev_mean_sea_level=on"
            f"&subregion=&toplat={NORTH}&leftlon={WEST}&rightlon={EAST}&bottomlat={SOUTH}")


def _get(url: str, tries: int = 3) -> bytes:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "rainmap-fetch/1.0"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = r.read()
            if data[:4] != b"GRIB":
                raise RuntimeError("คำตอบไม่ใช่ GRIB")
            return data
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"ดึง GFS ล้มเหลว: {last}")


def latest_cycle(now: datetime | None = None) -> datetime:
    """รอบล่าสุดที่มีไฟล์ชั่วโมงสุดท้ายพร้อมแล้ว (ลองย้อนทีละ 6 ชม. สูงสุด 4 รอบ)"""
    now = now or datetime.now(timezone.utc)
    c = now.replace(minute=0, second=0, microsecond=0)
    c -= timedelta(hours=c.hour % 6)
    for _ in range(5):
        try:
            _get(_url(c, HOURS), tries=1)
            return c
        except Exception:  # noqa: BLE001
            c -= timedelta(hours=6)
            time.sleep(PAUSE)
    raise RuntimeError("ไม่พบรอบ GFS ที่พร้อมใช้ใน 30 ชม. ล่าสุด")


def _apcp(msgs: list, fh: int, cum: dict):
    """ฝนสะสมที่จบที่ชั่วโมง fh: เลือกช่วงที่เริ่มจากชั่วโมงที่มีค่าสะสมแล้ว (ชอบช่วงยาวสุด ปกติคือ 0-fh)
    คืน (message, ชั่วโมงเริ่ม, ตาราง)"""
    best = None
    for m in msgs:
        if (m.cat, m.num) == (1, 8) and m.stat_type == 1 and m.forecast_hour + m.range_hours == fh and m.forecast_hour in cum:
            if best is None or m.forecast_hour < best.forecast_hour:
                best = m
    if best is None:
        raise RuntimeError(f"ไม่พบฝนสะสมที่จบ f{fh:03d} ในไฟล์")
    return best, best.forecast_hour, grib2.to_rows(best)


def _rain_code(v) -> int:
    """มม. ต่อช่วง -> uint8: 0-20 มม. ละเอียด 0.1, เกินนั้นละเอียด 2 มม. ถึง 128 มม., 255 = ไม่มีข้อมูล"""
    if v is None:
        return 255
    if v <= 20:
        return max(0, round(v * 10))
    return min(254, 200 + round((v - 20) / 2))


def _field(msgs: list, cat: int, num: int):
    """ตารางค่า ณ เวลานั้น (ลม / ความกดอากาศ) ย่อเหลือทุก WX_STEP จุด"""
    for m in msgs:
        if (m.cat, m.num) == (cat, num) and m.range_hours == 0:
            rows = grib2.to_rows(m)
            return [r[::WX_STEP] for r in rows[::WX_STEP]]
    raise RuntimeError(f"ไม่พบตัวแปร {cat}/{num} ในไฟล์")


def _tmp(msgs: list):
    """อุณหภูมิ 2 ม. ณ เวลานั้น (TMP) เป็นองศาเซลเซียส"""
    for m in msgs:
        if (m.cat, m.num) == (0, 0) and m.range_hours == 0 and m.level_type == 103 and round(m.level_value) == 2:
            return [[None if x is None else x - 273.15 for x in r] for r in grib2.to_rows(m)]
    raise RuntimeError("ไม่พบ TMP 2 ม. ในไฟล์ (ระวัง: var_TMP + lev_surface จะได้อุณหภูมิผิวพื้นมาด้วย)")


def current_init() -> str | None:
    p = OUT / "meta.json"
    if not p.exists() or not (OUT / "rain.bin").exists():
        return None
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
        ok = m.get("provider") == "noaa" and m.get("steps") and m.get("wx") and (OUT / "wind.bin").exists() and (OUT / "pres.bin").exists() and m.get("temp") and (OUT / "temp.bin").exists() and m.get("tnow") and (OUT / "tnow.bin").exists() and m.get("wnow") and (OUT / "wnow.bin").exists()
        return m.get("init") if ok else None
    except Exception:  # noqa: BLE001
        return None


def fetch(force: bool = False) -> dict:
    cycle = latest_cycle()
    init = cycle.strftime("%Y-%m-%dT%H:%MZ")
    if not force and current_init() == init:
        return {"init": init, "source": "gfs", "provider": "noaa", "skipped": True}

    msg0 = None
    cum = {0: None}         # fh -> ตารางฝนสะสมตั้งแต่ชั่วโมง 0 (None ที่ f000 = ศูนย์ทั้งหมด)
    steps = []              # ฝนแต่ละช่วง STEP_H ชม.
    wind = bytearray()      # ต่อเวลา: u int8 แล้ว v int8 หน่วย 0.5 ม./วินาที
    pres = []               # ต่อเวลา: uint16 = Pa - 85000
    wx_shape = None

    def add_wx(msgs):
        nonlocal wx_shape
        u, v, p = _field(msgs, 2, 2), _field(msgs, 2, 3), _field(msgs, 3, 1)
        wx_shape = (len(u[0]), len(u))
        for f in (u, v):
            for row in f:
                wind.extend(struct.pack("%db" % len(row), *[max(-127, min(127, round((x or 0) * 2))) for x in row]))
        for row in p:
            pres.extend(max(0, min(65535, round((x or 101300) - 85000))) for x in row)

    # อุณหภูมิต่ำสุด/สูงสุดของแต่ละวันตามปฏิทินไทย จาก TMIN/TMAX ทุกช่วงที่ GFS ให้มา
    local0 = (cycle + timedelta(hours=7)).date()
    tlo, thi = {}, {}                              # วัน k -> ตาราง (องศาเซลเซียส)

    def add_temp(msgs, fh):
        end = cycle + timedelta(hours=fh + 7)      # เวลาไทยที่ช่วงนั้นจบ
        k = (end.date() - local0).days
        if not 0 <= k < DAYS:
            return
        for num, stat, store, hours in ((5, 3, tlo, MIN_END), (4, 2, thi, MAX_END)):
            if end.hour not in hours:
                continue
            for m in msgs:
                if (m.cat, m.num) == (0, num) and m.stat_type == stat and m.range_hours > 0 and m.forecast_hour + m.range_hours == fh:
                    start = end - timedelta(hours=m.range_hours)
                    # ช่วงต้องครอบเวลาที่ร้อน/เย็นที่สุดจริง: ต่ำสุดต้องเริ่มก่อน 06:00 น., สูงสุดต้องครอบ 13:00-16:00 น.
                    if num == 5 and not (start.date() < end.date() or start.hour <= 6):
                        continue
                    if num == 4 and not (start.hour <= 13 and end.hour >= 16):
                        continue
                    rows = [[None if x is None else x - 273.15 for x in r] for r in grib2.to_rows(m)]
                    old = store.get(k)
                    if old is None:
                        store[k] = rows
                    else:
                        pick = min if num == 5 else max
                        store[k] = [[b if a is None else a if b is None else pick(a, b) for a, b in zip(ra, rb)] for ra, rb in zip(old, rows)]
                    break

    step_fhs = list(range(0, HOURS + 1, STEP_H))
    now_fhs = list(range(0, NOW_HOURS + 1))
    tnow = {}                                      # fh -> ตารางอุณหภูมิ ณ ชั่วโมงนั้น
    wnow = {}                                      # fh -> bytes ลม u แล้ว v ณ ชั่วโมงนั้น
    for fh in sorted(set(step_fhs) | set(now_fhs)):
        msgs = grib2.parse(_get(_url(cycle, fh)))
        if fh in now_fhs:
            tnow[fh] = _tmp(msgs)
            b = bytearray()
            for f in (_field(msgs, 2, 2), _field(msgs, 2, 3)):
                for row in f:
                    b.extend(struct.pack("%db" % len(row), *[max(-127, min(127, round((x or 0) * 2))) for x in row]))
            wnow[fh] = bytes(b)
        if fh % STEP_H:
            time.sleep(PAUSE)
            continue
        add_wx(msgs)
        if fh == 0:                                # f000 = ค่าวิเคราะห์ ณ เวลา init (ไม่มีฝนสะสม)
            time.sleep(PAUSE)
            continue
        add_temp(msgs, fh)
        m, s0, rows = _apcp(msgs, fh, cum)
        msg0 = msg0 or m
        base = cum[s0]
        cum[fh] = rows if base is None else [[(a + b) if a is not None and b is not None else None for a, b in zip(ra, rb)]
                                              for ra, rb in zip(rows, base)]
        prev = cum[fh - STEP_H]
        steps.append(cum[fh] if prev is None else [[max(0.0, a - b) if a is not None and b is not None else None for a, b in zip(ra, rb)]
                                                    for ra, rb in zip(cum[fh], prev)])
        time.sleep(PAUSE)

    lat0, lon0, dlat, dlon = grib2.lat_lon_of(msg0)
    nx, ny = msg0.grid.ni, msg0.grid.nj
    rb = bytearray()
    for st in steps:
        for row in st:
            rb.extend(_rain_code(v) for v in row)
    assert len(rb) == NSTEPS * nx * ny

    w, e = lon0 - dlon / 2, lon0 + (nx - 1) * dlon + dlon / 2
    s_, n = lat0 - dlat / 2, lat0 + (ny - 1) * dlat + dlat / 2
    meta = {
        "init": init,
        "source": "gfs",
        "provider": "noaa",
        "sample": False,
        "attribution": "Forecast rain: NOAA GFS 0.25 deg (NOMADS)",
        "corners": [[w, n], [e, n], [e, s_], [w, s_]],
        "steps": {"start": init, "stepHours": STEP_H, "count": NSTEPS},
        "grid": {"lat0": lat0, "lon0": lon0, "dlat": dlat, "dlon": dlon, "ny": ny, "nx": nx,
                 "file": "rain.bin", "dtype": "uint8", "order": "step, row, col",
                 "decode": "mm per step: v <= 200 -> v / 10, else 20 + (v - 200) * 2; 255 = no data"},
        "levels": {"step": [0.5, 2, 5, 10, 20, 40]},
        "wx": {"lat0": lat0, "lon0": lon0, "dlat": dlat * WX_STEP, "dlon": dlon * WX_STEP, "nx": wx_shape[0], "ny": wx_shape[1],
               "times": NSTEPS + 1, "stepHours": STEP_H,
               "wind": {"file": "wind.bin", "dtype": "int8", "scale": 0.5, "order": "time, u then v, row, col"},
               "pres": {"file": "pres.bin", "dtype": "uint16", "offsetPa": 85000}},
        "temp": {"file": "temp.bin", "dtype": "uint8", "decode": "v / 2 - 40 (degC), 255 = no data", "order": "day, min then max, row, col",
                 "days": DAYS, "dates": [(local0 + timedelta(days=k)).isoformat() for k in range(DAYS)],
                 "minWindow": "GFS TMIN ending 04:00-10:00 ICT", "maxWindow": "GFS TMAX ending 13:00-19:00 ICT",
                 "have": [[k in tlo, k in thi] for k in range(DAYS)]},
        "tnow": {"file": "tnow.bin", "dtype": "uint8", "decode": "v / 2 - 40 (degC), 255 = no data", "order": "hour, row, col",
                 "start": init, "stepHours": 1, "hours": NOW_HOURS + 1},
        "wnow": {"file": "wnow.bin", "dtype": "int8", "scale": 0.5, "order": "hour, u then v, row, col (wx grid)",
                 "start": init, "stepHours": 1, "hours": NOW_HOURS + 1},
        "notes": [f"NOAA GFS 0.25 deg APCP; rain per {STEP_H} h step k = accumulated at f({STEP_H}k+{STEP_H}) minus f({STEP_H}k)",
                  "wind/pressure at f(3t); 2 m temperature: min/max of GFS TMIN/TMAX windows per Thai calendar day"],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "rain.bin").write_bytes(bytes(rb))
    (OUT / "wind.bin").write_bytes(bytes(wind))
    (OUT / "pres.bin").write_bytes(struct.pack("<%dH" % len(pres), *pres))
    tb = bytearray([255]) * (DAYS * 2 * nx * ny)
    for which, store in ((0, tlo), (1, thi)):
        for k, rows in store.items():
            off = (k * 2 + which) * nx * ny
            for j, row in enumerate(rows):
                for i, v in enumerate(row):
                    if v is not None:
                        tb[off + j * nx + i] = max(0, min(254, round((v + 40) * 2)))
    (OUT / "temp.bin").write_bytes(bytes(tb))
    nb = bytearray([255]) * ((NOW_HOURS + 1) * nx * ny)
    for fh, rows in tnow.items():
        off = fh * nx * ny
        for j, row in enumerate(rows):
            for i, v in enumerate(row):
                if v is not None:
                    nb[off + j * nx + i] = max(0, min(254, round((v + 40) * 2)))
    (OUT / "tnow.bin").write_bytes(bytes(nb))
    wsize = 2 * wx_shape[0] * wx_shape[1]
    (OUT / "wnow.bin").write_bytes(b"".join(wnow.get(fh, bytes(wsize)) for fh in now_fhs))
    (OUT / "daily.bin").unlink(missing_ok=True)    # รูปแบบเก่า (ฝนรายวัน 15 วัน)
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return {"init": init, "source": "gfs", "provider": "noaa", "grid": f"{nx}x{ny}", "steps": NSTEPS, "skipped": False}


if __name__ == "__main__":
    import sys
    print(fetch(force="--force" in sys.argv))
