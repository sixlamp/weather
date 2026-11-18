/* หน้าชลประทาน: ภาพรวม 22 ลุ่มน้ำหลัก และอ่างเก็บน้ำขนาดใหญ่
   ข้อมูล: data/water/*.json (fetch_water.py ดึงจากระบบสมดุลน้ำ กรมชลประทาน ทุก 6 ชม.)
   ขอบลุ่มน้ำ: water_basins.png (tools/build_basins.py) ค่าพิกเซล = รหัสลุ่มน้ำ บนกริด 0.01 องศา
   ลุ่มน้ำ: สีพื้นเข้มตามฝน 24 ชม. เฉลี่ยในลุ่ม (แทนแท่งทรงกระบอกของต้นทาง) ป้ายชื่อเป็นสีตามสถานะระดับน้ำในลำน้ำ
   อ่าง: ป้าย % ความจุ สีตามช่วงของ ชป. (SWOC)
   แม่น้ำ: water_rivers.json (tools/build_rivers.py จาก OpenStreetMap) แสดงทั้ง 2 โหมด
   ฝนล่าสุดจากเรดาร์และเมฆจากดาวเทียม (ชุดเดียวกับหน้าอากาศวันนี้) app.js เป็นคนวาด ผ่าน ui.wx() */
window.RainWater = function (map, ui) {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const num = (v, d = 0) => (v == null ? '-' : Number(v).toLocaleString('th-TH', { minimumFractionDigits: d, maximumFractionDigits: d }));
  map.createPane('waterPane').style.zIndex = 350;          // เหนือเมฆ (300) ใต้ภาพฝน (400) เส้นเขตแดน (460) และชื่อ (470)
  map.getPane('waterPane').style.pointerEvents = 'none';
  map.createPane('waterMarkPane').style.zIndex = 480;      // ป้ายลุ่มน้ำ/อ่าง อยู่เหนือชื่อเมือง
  map.createPane('riverPane').style.zIndex = 440;          // แม่น้ำอยู่เหนือภาพฝน จะได้เห็นว่าฝนตกตรงลำน้ำไหน
  const riverRenderer = L.canvas({ pane: 'riverPane', tolerance: 8 });

  // สถานะระดับน้ำในลำน้ำ (ระดับของสถานีเทียบตลิ่ง ตามเกณฑ์ของ ThaiWater)
  const LV = {
    5: { name: 'ล้นตลิ่ง', long: 'น้ำล้นตลิ่ง (>100%)', col: '#d62828' },
    4: { name: 'น้ำมาก', long: 'น้ำมาก (>70%)', col: '#ef7d00' },
    3: { name: 'ปกติ', long: 'น้ำปกติ (>30%)', col: '#2b8a3e' },
    2: { name: 'น้ำน้อย', long: 'น้ำน้อย (>10%)', col: '#c99700' },
    1: { name: 'น้อยวิกฤต', long: 'น้ำน้อยวิกฤต (<=10%)', col: '#8d5524' },
  };
  // ช่วง % ความจุอ่าง (ชป. SWOC)
  const BAND = [
    { min: 100.0001, name: 'เกินความจุเก็บกักปกติ', short: '>100%', col: '#d62828' },
    { min: 80.0001, name: 'น้ำมาก', short: '81-100%', col: '#ef7d00' },
    { min: 50.0001, name: 'ปกติ', short: '51-80%', col: '#1f6feb' },
    { min: 30.0001, name: 'น้ำน้อย', short: '31-50%', col: '#c99700' },
    { min: -1, name: 'น้ำน้อยวิกฤต', short: '<=30%', col: '#8d5524' },
  ];
  const band = (p) => BAND.find((b) => (p == null ? -1 : p) >= b.min) || BAND[BAND.length - 1];
  // ฝน 24 ชม. เฉลี่ยในลุ่ม (มม.) -> ความเข้มสีฟ้า
  const RAIN_LV = [1, 5, 10, 20, 35, 60];
  const RAIN_COL = [[205, 228, 255], [140, 195, 255], [70, 150, 245], [35, 100, 220], [60, 50, 190], [120, 30, 160]];
  function rainRGBA(mm) {
    if (mm == null) return [150, 150, 150, 40];
    if (mm < RAIN_LV[0]) return [205, 228, 255, Math.round(25 + 40 * Math.max(0, mm))];
    let i = 0; while (i < RAIN_LV.length - 1 && mm >= RAIN_LV[i + 1]) i++;
    const t = i < RAIN_LV.length - 1 ? (mm - RAIN_LV[i]) / (RAIN_LV[i + 1] - RAIN_LV[i]) : 0, a = RAIN_COL[i], b = RAIN_COL[Math.min(i + 1, RAIN_COL.length - 1)];
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, 120 + 15 * i];
  }

  const st = { mode: 'basin', on: false, basins: null, dams: null, loadedAt: 0, ids: null, G: null, overlay: null, imgKey: '', marks: L.layerGroup(), dark: true, loading: null };
  try { const m = localStorage.getItem('rainmap.water'); if (m === 'dam' || m === 'basin') st.mode = m; } catch (e) { /* ใช้ค่าเริ่มต้น */ }
  // ชั้นเสริมของหน้านี้ เปิดไว้ตั้งแต่แรก: เห็นทันทีว่าลุ่ม/อ่างไหนกำลังมีฝน (แยกจากปุ่มของหน้าอากาศวันนี้)
  const lay = { rain: true, cloud: true, river: true };
  try { Object.assign(lay, JSON.parse(localStorage.getItem('rainmap.waterLayers') || '{}')); } catch (e) { /* ใช้ค่าเริ่มต้น */ }
  const rv = { data: null, group: L.layerGroup(), key: '', loading: null };

  async function getJson(u) { const r = await fetch(u + '?t=' + Date.now()); if (!r.ok) throw new Error(u + ' ' + r.status); return r.json(); }
  function loadIds() {
    return Promise.all([getJson('water_basins.json'), new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => rej(new Error('water_basins.png')); i.src = 'water_basins.png'; })])
      .then(([G, img]) => {
        const cv = document.createElement('canvas'); cv.width = img.width; cv.height = img.height;
        const ctx = cv.getContext('2d', { willReadFrequently: true }); ctx.drawImage(img, 0, 0);
        const d = ctx.getImageData(0, 0, cv.width, cv.height).data, ids = new Uint8Array(cv.width * cv.height);
        for (let k = 0; k < ids.length; k++) ids[k] = d[k * 4];
        st.ids = ids; st.G = { ...G, W: img.width, H: img.height };
      });
  }
  function load() {
    if (st.loading) return st.loading;
    st.loading = Promise.all([getJson('data/water/basins.json'), getJson('data/water/dams.json'), st.ids ? null : loadIds()])
      .then(([b, d]) => { st.basins = b; st.dams = d; st.loadedAt = Date.now(); st.imgKey = ''; })
      .finally(() => { st.loading = null; });
    return st.loading;
  }

  // ภาพลุ่มน้ำแบบ Web Mercator (แปลงแถวตามละติจูด ภาพจึงตรงกับแผนที่ทุกระดับซูม)
  const merc = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
  const unmerc = (y) => (Math.atan(Math.exp(y)) * 360) / Math.PI - 90;
  function basinImage(fill) {
    const G = st.G, W = G.W, H = G.H, ids = st.ids, yN = merc(G.n), yS = merc(G.s);
    const col = new Array(256).fill(null);
    for (const b of st.basins.basins) col[b.id] = fill ? rainRGBA(b.rain && b.rain.mean) : null;
    const line = st.dark ? [255, 255, 255, 150] : [40, 50, 70, 150];
    const cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    const ctx = cv.getContext('2d'), im = ctx.createImageData(W, H), px = im.data;
    const rowOf = new Int32Array(H);
    for (let y = 0; y < H; y++) rowOf[y] = Math.min(H - 1, Math.max(0, Math.floor((G.n - unmerc(yN - ((y + 0.5) / H) * (yN - yS))) / G.d)));
    for (let y = 0; y < H; y++) {
      const r = rowOf[y], ru = rowOf[Math.max(0, y - 1)], rd = rowOf[Math.min(H - 1, y + 1)];
      for (let x = 0; x < W; x++) {
        const id = ids[r * W + x]; if (!id) continue;
        const p = (y * W + x) * 4;
        // ขอบลุ่ม: ช่องข้าง ๆ เป็นลุ่มอื่น (หรือนอกประเทศ เว้นไว้ไม่ขีด)
        const nb = [x > 0 ? ids[r * W + x - 1] : id, x < W - 1 ? ids[r * W + x + 1] : id, ids[ru * W + x], ids[rd * W + x]];
        if (nb.some((v) => v && v !== id)) { px[p] = line[0]; px[p + 1] = line[1]; px[p + 2] = line[2]; px[p + 3] = line[3]; continue; }
        const c = col[id]; if (!c) continue;
        px[p] = c[0]; px[p + 1] = c[1]; px[p + 2] = c[2]; px[p + 3] = c[3];
      }
    }
    ctx.putImageData(im, 0, 0);
    return cv.toDataURL('image/png');
  }
  function drawBasins(fill) {
    const key = (fill ? 'f' : 'o') + ':' + st.dark + ':' + st.loadedAt;
    const G = st.G, bounds = L.latLngBounds([G.s, G.w], [G.n, G.e]);
    if (key !== st.imgKey) {
      st.imgKey = key;
      const url = basinImage(fill);
      if (!st.overlay) st.overlay = L.imageOverlay(url, bounds, { pane: 'waterPane', interactive: false });
      else st.overlay.setUrl(url);
    }
    if (!map.hasLayer(st.overlay)) st.overlay.addTo(map);
  }

  function basinPopup(b) {
    const lv = LV[b.worst] || LV[3], c = b.counts || {};
    let h = `<b>ลุ่มน้ำ${esc(b.name)}</b><br>ลำน้ำ: <b style="color:${lv.col}">${lv.name}</b> (สถานีที่สูงที่สุดเทียบตลิ่ง)`;
    h += `<br>สถานีวัดระดับน้ำ ${b.n || 0} สถานี: ` + [5, 4, 3, 2, 1].filter((k) => c[k]).map((k) => `${LV[k].name} ${c[k]}`).join(', ');
    const r = b.rain || {};
    h += `<br>ฝน 24 ชม. เฉลี่ยในลุ่ม <b>${r.mean == null ? '-' : num(r.mean, 1) + ' มม.'}</b>` + (r.max ? ` (มากสุด ${num(r.max, 1)} มม. ที่ ${esc(r.maxAt)})` : '');
    const top = (b.stations || []).filter((s) => s.pct != null).sort((x, y) => y.pct - x.pct).slice(0, 3);
    if (top.length) h += '<br><span class="small">สถานีที่น้ำสูงสุด:</span>' + top.map((s) => `<br>&bull; ${esc(s.name)} ${esc(s.river || '')} <b>${num(s.pct)}%</b> ของตลิ่ง`).join('');
    return h;
  }
  function damPopup(d) {
    const b = band(d.pct);
    return `<b>อ่างเก็บน้ำ${esc(d.name)}</b><br><span class="small">${esc(d.prov || '')} | ${esc(d.basin || '')} | ${esc(d.agency || '')}</span>`
      + `<br>ปริมาณน้ำ <b style="color:${b.col}">${num(d.pct)}%</b> ของความจุที่ระดับเก็บกักปกติ (${b.name})`
      + `<br>${num(d.storageMcm, 1)} / ${num(d.normalMcm, 1)} ล้าน ลบ.ม. | ใช้การได้ ${num(d.usableMcm, 1)} ล้าน ลบ.ม. (${num(d.usablePct)}%)`
      + `<br>ไหลเข้า ${num(d.inflowMcm, 2)} | ระบาย ${num(d.releasedMcm, 2)} ล้าน ลบ.ม./วัน`
      + `<br><span class="small">ข้อมูลวันที่ ${esc(d.date || '-')}</span>`;
  }

  // ป้ายชื่อลุ่มน้ำที่ทับกัน: ลุ่มที่สถานะหนักกว่า (แล้วฝนมากกว่า) ได้แสดงชื่อ ที่เหลือย่อเป็นจุดสี แตะได้เหมือนเดิม
  let basinMarks = [];
  const mctx = document.createElement('canvas').getContext('2d');
  const textW = (t) => { mctx.font = '600 12px sans-serif'; return mctx.measureText(t).width; };
  function declutter() {
    if (!st.on) return;
    const boxes = [];
    for (const m of basinMarks) {
      const p = map.latLngToContainerPoint(m.getLatLng()), w = m._w, h = 18;
      const box = [p.x - w / 2, p.y - h / 2, p.x + w / 2, p.y + h / 2];
      const hit = boxes.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1]);
      if (!hit) boxes.push(box);
      if (m._full !== !hit) { m._full = !hit; m.setIcon(hit ? m._dot : m._lbl); }
    }
  }
  map.on('zoomend', declutter);

  function drawMarks() {
    st.marks.clearLayers(); basinMarks = [];
    if (st.mode === 'basin') {
      const order = st.basins.basins.filter((b) => b.center).sort((a, b) => (b.worst || 0) - (a.worst || 0) || ((b.rain && b.rain.mean) || 0) - ((a.rain && a.rain.mean) || 0));
      for (const b of order) {
        const lv = LV[b.worst] || LV[3];
        const lbl = L.divIcon({ className: 'wb-lbl', html: `<span style="background:${lv.col}">${esc(b.name)}</span>`, iconSize: null });
        const dot = L.divIcon({ className: 'wb-dot', html: `<span style="background:${lv.col}" title="${esc(b.name)}"></span>`, iconSize: null });
        const m = L.marker([b.center[1], b.center[0]], { pane: 'waterMarkPane', icon: lbl }).bindPopup(() => basinPopup(b), { maxWidth: 280 }).addTo(st.marks);
        m._lbl = lbl; m._dot = dot; m._full = true; m._w = textW(b.name) + 18;
        basinMarks.push(m);
      }
    } else {
      // อ่างที่น้ำมากหรือน้อยผิดปกติได้แสดงตัวเลขก่อน
      const extreme = (p) => Math.abs((p == null ? 65 : p) - 65);
      for (const d of st.dams.items.slice().sort((a, b) => extreme(b.pct) - extreme(a.pct))) {
        const b = band(d.pct), t = `${num(d.pct)}%`;
        const lbl = L.divIcon({ className: 'wd-lbl', html: `<span style="background:${b.col}" title="${esc(d.name)}">${t}</span>`, iconSize: null });
        const dot = L.divIcon({ className: 'wb-dot', html: `<span style="background:${b.col}" title="${esc(d.name)} ${t}"></span>`, iconSize: null });
        const m = L.marker([d.lat, d.lon], { pane: 'waterMarkPane', icon: lbl }).bindPopup(() => damPopup(d), { maxWidth: 280 }).addTo(st.marks);
        m._lbl = lbl; m._dot = dot; m._full = true; m._w = textW(t) + 12;
        basinMarks.push(m);
      }
    }
    if (!map.hasLayer(st.marks)) st.marks.addTo(map);
    declutter();
  }

  // ---------- แม่น้ำ ----------
  function loadRivers() {
    if (!rv.loading) rv.loading = getJson('water_rivers.json').then((d) => { rv.data = d; }).catch((e) => { rv.loading = null; throw e; });
    return rv.loading;
  }
  const RW = [0, 1, 1.7, 2.6];        // ความหนาตามขนาดแม่น้ำ (1 สายรอง .. 3 สายหลัก)
  function drawRivers() {
    if (!st.on || !lay.river) { if (map.hasLayer(rv.group)) map.removeLayer(rv.group); return; }
    if (!rv.data) { loadRivers().then(drawRivers).catch(() => { /* ไม่มีเส้นแม่น้ำก็ใช้หน้านี้ได้ */ }); return; }
    const z = map.getZoom(), f = z >= 9 ? 1.8 : z >= 8 ? 1.4 : z >= 7 ? 1.15 : 1;
    const key = st.dark + ':' + f;
    if (key !== rv.key) {
      rv.key = key; rv.group.clearLayers();
      const col = st.dark ? '#9ee9ff' : '#0b5cad', halo = st.dark ? 'rgba(10,20,40,.55)' : 'rgba(255,255,255,.8)';
      for (const r of rv.data.rivers) {
        const ll = r.l.map((line) => line.map((p) => [p[1], p[0]]));
        L.polyline(ll, { renderer: riverRenderer, color: halo, weight: RW[r.w] * f + 2, opacity: 1, interactive: false }).addTo(rv.group);
      }
      for (const r of rv.data.rivers) {
        const ll = r.l.map((line) => line.map((p) => [p[1], p[0]]));
        L.polyline(ll, { renderer: riverRenderer, color: col, weight: RW[r.w] * f, opacity: 0.95 })
          .bindPopup(`<b>${esc(r.n)}</b><br><span class="small">ความยาวในไทยประมาณ ${num(r.km)} กม. (จาก OpenStreetMap)</span>`, { maxWidth: 240 })
          .addTo(rv.group);
      }
    }
    if (!map.hasLayer(rv.group)) rv.group.addTo(map);
  }
  map.on('zoomend', () => { if (st.on) drawRivers(); });

  function layerButtons() {
    document.querySelectorAll('#waterLayers button').forEach((b) => b.classList.toggle('active', !!lay[b.dataset.w]));
  }
  document.querySelectorAll('#waterLayers button').forEach((b) => {
    b.onclick = () => {
      lay[b.dataset.w] = !lay[b.dataset.w];
      try { localStorage.setItem('rainmap.waterLayers', JSON.stringify(lay)); } catch (e) { /* ข้ามได้ */ }
      layerButtons(); drawRivers(); ui.wx(); legendNow(); ui.credits();
    };
  });

  function legendNow() {
    if (st.mode === 'basin') {
      const chips = [5, 4, 3, 2, 1].map((k) => `<span class="wl-chip" style="background:${LV[k].col}">${LV[k].name}</span>`).join(' ');
      ui.legend('ฝน 24 ชม. เฉลี่ยในลุ่ม (มม.)', RAIN_LV, RAIN_COL, '', `สีป้ายชื่อ = ระดับน้ำในลำน้ำ (สถานีที่สูงที่สุดในลุ่มเทียบตลิ่ง):<br>${chips}${extraNote()}<br>แตะป้ายชื่อหรือจุดเพื่อดูรายละเอียด`);
    } else {
      ui.legendRows('อ่างเก็บน้ำขนาดใหญ่ (% ความจุ)', BAND.map((b) => [b.col, `${b.short} ${b.name}`]), `${st.dams ? st.dams.items.length : ''} อ่าง | % ของความจุที่ระดับเก็บกักปกติ ตามช่วงของ ชป. (SWOC)${extraNote()}<br>แตะป้ายเพื่อดูรายละเอียด`);
    }
  }
  function extraNote() {
    const t = [];
    if (lay.rain) t.push('ฝนตอนนี้ = ภาพเรดาร์ล่าสุด (สีเดียวกับหน้าอากาศวันนี้)');
    if (lay.cloud) t.push('สีขาว = เมฆจากดาวเทียม');
    if (lay.river) t.push('เส้นฟ้า = แม่น้ำสายหลัก แตะเพื่อดูชื่อ');
    return t.length ? '<br>' + t.join(' | ') : '';
  }
  function header() {
    document.querySelectorAll('#waterMode button').forEach((b) => b.classList.toggle('active', b.dataset.m === st.mode));
    const k = $('waterKind');
    if (!st.basins) { k.textContent = st.err ? 'โหลดข้อมูลไม่ได้: ' + st.err : 'กำลังโหลด'; k.classList.toggle('err', !!st.err); return; }
    k.classList.remove('err');
    k.textContent = st.mode === 'basin'
      ? `ระดับน้ำ ${String(st.basins.waterlevelTime || '').slice(11, 16)} น. | ฝน 24 ชม. ถึง ${String(st.basins.rain24Time || '').slice(11, 16)} น.`
      : `ข้อมูลอ่างวันที่ ${esc((st.dams.items[0] || {}).date || '-')}`;
  }
  function render() {
    if (!st.on) return;
    header();
    if (!st.basins) return;
    drawBasins(st.mode === 'basin');
    drawRivers();
    drawMarks();
    legendNow();
    ui.credits();
  }
  // ป๊อปอัปขึ้นเฉพาะตอนแตะป้ายชื่อหรือจุดของลุ่มน้ำ แตะพื้นที่อื่นบนแผนที่ไม่ขึ้น (ไม่กวนตอนเลื่อนดูแผนที่)
  document.querySelectorAll('#waterMode button').forEach((b) => {
    b.onclick = () => {
      st.mode = b.dataset.m;
      try { localStorage.setItem('rainmap.water', st.mode); } catch (e) { /* ข้ามได้ */ }
      map.closePopup(); render();
    };
  });

  return {
    enter() {
      st.on = true; header(); layerButtons(); drawRivers();
      if (!st.basins || Date.now() - st.loadedAt > 30 * 60e3) {
        load().then(() => { st.err = null; render(); }).catch((e) => { st.err = e.message; header(); });
      }
      render();
    },
    leave() {
      st.on = false; map.closePopup();
      if (st.overlay && map.hasLayer(st.overlay)) map.removeLayer(st.overlay);
      if (map.hasLayer(st.marks)) map.removeLayer(st.marks);
      if (map.hasLayer(rv.group)) map.removeLayer(rv.group);
    },
    layers: () => lay,
    setDark(v) { st.dark = v; if (st.on) render(); },
    when: () => (st.basins ? (st.mode === 'basin' ? st.basins.made : st.dams.fetched) : null),
    source: () => 'ข้อมูลน้ำ: คลังข้อมูลน้ำแห่งชาติ (ThaiWater) สสน. และหน่วยงานเจ้าของสถานี/อ่าง ผ่านระบบสมดุลน้ำ กรมชลประทาน (ทดลอง) | ขอบลุ่มน้ำประมาณจาก HydroBASINS'
      + (lay.river ? ' | แม่น้ำ: © OpenStreetMap contributors' : ''),
  };
};
