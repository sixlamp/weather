// rid-proxy: Cloudflare Worker ทางผ่าน https ไปยังเรดาร์ของระบบสมดุลน้ำ กรมชลประทาน (เซิร์ฟเวอร์เป็น http
// หน้าเว็บบน GitHub Pages ซึ่งเป็น https จึงดึงตรงไม่ได้) ให้แหล่ง "ไทย" ได้ภาพล่าสุดทันทีโดยไม่ต้องรอ GitHub Actions
//
// ความปลอดภัย: ผ่านได้เฉพาะ GET ของ 2 แบบนี้ และตอบเฉพาะคำขอที่มาจากเว็บ RainMap
//   /obs/radar/index.json
//   /obs/radar/frames/<ชื่อไฟล์>.png
// deploy: วางไฟล์นี้ใน Cloudflare dashboard > Workers & Pages > rid-proxy > Edit code แล้วกด Deploy
// Cloudflare ไม่ให้ Worker ดึงจากที่อยู่ IP ตรง ๆ (ตอบ 403) จึงใช้ชื่อโฮสต์ของ sslip.io ที่ชี้กลับไป IP เดิม
const UPSTREAM = 'http://183-88-230-184.sslip.io:8002/waterbalance/data';
const ORIGINS = ['https://nabogus.github.io', 'http://127.0.0.1:8791', 'http://localhost:8791'];
const INDEX = '/obs/radar/index.json';
const FRAME = /^\/obs\/radar\/frames\/[A-Za-z0-9_]+\.png$/;

export default {
  async fetch(request) {
    const origin = request.headers.get('Origin') || '';
    const cors = ORIGINS.includes(origin) ? { 'Access-Control-Allow-Origin': origin, Vary: 'Origin' } : null;
    if (request.method === 'OPTIONS' && cors) return new Response(null, { status: 204, headers: { ...cors, 'Access-Control-Allow-Methods': 'GET' } });
    if (request.method !== 'GET') return new Response('method not allowed', { status: 405 });
    if (!cors) return new Response('forbidden', { status: 403 });

    const path = new URL(request.url).pathname;
    const isIndex = path === INDEX;
    if (!isIndex && !FRAME.test(path)) return new Response('not found', { status: 404, headers: cors });

    // index เปลี่ยนทุก 15 นาที: cache 60 วินาที / ไฟล์ภาพชื่อไม่ซ้ำ: cache 1 วัน
    const ttl = isIndex ? 60 : 86400;
    let up;
    try {
      up = await fetch(UPSTREAM + path, { cf: { cacheTtl: ttl, cacheEverything: true }, signal: AbortSignal.timeout(20000) });
    } catch (e) {
      return new Response('upstream down', { status: 502, headers: cors });
    }
    if (!up.ok) return new Response('upstream ' + up.status, { status: 502, headers: cors });
    return new Response(up.body, {
      headers: { ...cors, 'Content-Type': isIndex ? 'application/json; charset=utf-8' : 'image/png', 'Cache-Control': `public, max-age=${ttl}` },
    });
  },
};
