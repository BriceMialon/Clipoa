// Bibliotheque de decors, accessoires et personnages "blocky" (style jouet low-poly).
import * as THREE from 'three';
import { mat, rbox, finMesh } from './shark.js';

export const PAL = {
  sky: '#86bff2', skyH: '#e4f3ff', grass: '#7cbc5c', grassDark: '#5d9b45', cobble: '#d8cdbb',
  brick: '#b5523b', cream: '#efe2c4', sky2: '#9cc7e0', butter: '#f2d58b', mint: '#a8d5b5', rose: '#e8a3a0',
  roofSlate: '#4e5d79', roofTerra: '#b5583e', roofBrown: '#6b4a3a', wood: '#c79a6b', woodDark: '#7a5236',
  windowDay: '#cfe8f7', windowNight: '#ffcf6b', door: '#2f5d50', stone: '#d9d2c3',
  gain: '#2ecc71', loss: '#e74c3c', gold: '#f1c40f', yellow: '#ffe600',
};

const at = (o, x, y, z) => { o.position.set(x, y, z); return o; };
const shadow = (o) => { o.traverse((m) => { if (m.isMesh) { m.castShadow = true; m.receiveShadow = true; } }); return o; };

export function canvasTex(w, h, draw) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const g = c.getContext('2d'); draw(g, w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  t.userData = { canvas: c, ctx: g, draw };
  return t;
}

export function textTex(text, o = {}) {
  const { w = 512, h = 128, bg = '#f4ead8', fg = '#2b2b2b', font = '900 80px Montserrat, Arial Black, sans-serif', stroke = null, border = null } = o;
  return canvasTex(w, h, (g) => {
    if (bg) { g.fillStyle = bg; g.fillRect(0, 0, w, h); }
    if (border) { g.strokeStyle = border; g.lineWidth = 10; g.strokeRect(5, 5, w - 10, h - 10); }
    g.font = font; g.textAlign = 'center'; g.textBaseline = 'middle';
    if (stroke) { g.lineWidth = 14; g.strokeStyle = stroke; g.lineJoin = 'round'; g.strokeText(text, w / 2, h / 2 + 4); }
    g.fillStyle = fg; g.fillText(text, w / 2, h / 2 + 4);
  });
}

export function plane(w, h, tex, opts = {}) {
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.8, transparent: !!opts.transparent, alphaTest: opts.transparent ? 0.05 : 0, side: opts.double ? THREE.DoubleSide : THREE.FrontSide, emissive: opts.emissive ? '#ffffff' : '#000000', emissiveMap: opts.emissive ? tex : null, emissiveIntensity: opts.emissive || 0 }));
  m.receiveShadow = true;
  return m;
}

const faceCache = new Map();
// expr : neutral|smile|worried|shocked|angry|shout|laugh ; suffixe '|b' = yeux fermes (clignement), '|o' = bouche ouverte (parole)
export function faceTex(key = 'neutral') {
  if (faceCache.has(key)) return faceCache.get(key);
  const [expr, flags = ''] = key.split('|');
  const blink = flags.includes('b'), open = flags.includes('o');
  const t = canvasTex(256, 256, (g) => {
    g.clearRect(0, 0, 256, 256);
    g.fillStyle = '#1b1b1f'; g.strokeStyle = '#1b1b1f'; g.lineCap = 'round'; g.lineWidth = 9;
    const eye = (x, y, rx = 15, ry = 23) => {
      if (blink) { g.beginPath(); g.moveTo(x - rx - 2, y + 2); g.quadraticCurveTo(x, y + 12, x + rx + 2, y + 2); g.stroke(); return; }
      g.beginPath(); g.ellipse(x, y, rx, ry, 0, 0, Math.PI * 2); g.fill(); g.fillStyle = '#fff'; g.beginPath(); g.arc(x - 4, y - 8, 5, 0, Math.PI * 2); g.fill(); g.fillStyle = '#1b1b1f'; };
    const brow = (x1, y1, x2, y2) => { g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke(); };
    const talk = (y = 168, rx = 20, ry = 15) => { g.beginPath(); g.ellipse(128, y, rx, ry, 0, 0, Math.PI * 2); g.fill(); g.fillStyle = '#c8505a'; g.beginPath(); g.ellipse(128, y + ry * 0.45, rx * 0.6, ry * 0.4, 0, 0, Math.PI * 2); g.fill(); g.fillStyle = '#1b1b1f'; };
    if (expr === 'laugh') {
      g.lineWidth = 10; g.beginPath(); g.arc(78, 112, 18, Math.PI * 1.1, Math.PI * 1.9); g.stroke(); g.beginPath(); g.arc(178, 112, 18, Math.PI * 1.1, Math.PI * 1.9); g.stroke();
      if (open) { g.beginPath(); g.moveTo(84, 152); g.quadraticCurveTo(128, 214, 172, 152); g.closePath(); g.fill(); }
      else { g.beginPath(); g.moveTo(80, 150); g.quadraticCurveTo(128, 230, 176, 150); g.closePath(); g.fill(); g.fillStyle = '#e8606a'; g.beginPath(); g.ellipse(128, 188, 24, 12, 0, 0, Math.PI * 2); g.fill(); }
    } else {
      eye(80, 112); eye(176, 112);
      if (expr === 'smile') { if (open) talk(160, 24, 16); else { g.beginPath(); g.arc(128, 140, 42, 0.15 * Math.PI, 0.85 * Math.PI); g.stroke(); } }
      else if (expr === 'worried') { brow(58, 76, 98, 66); brow(198, 76, 158, 66); if (open) talk(176, 16, 13); else { g.beginPath(); g.moveTo(96, 178); g.quadraticCurveTo(112, 164, 128, 176); g.quadraticCurveTo(144, 188, 160, 172); g.stroke(); } }
      else if (expr === 'shocked') { brow(60, 62, 100, 58); brow(156, 58, 196, 62); g.beginPath(); g.ellipse(128, 178, open ? 12 : 16, open ? 14 : 22, 0, 0, Math.PI * 2); g.fill(); }
      else if (expr === 'angry') { brow(58, 64, 102, 84); brow(198, 64, 154, 84); if (open) talk(176, 22, 12); else { g.beginPath(); g.moveTo(100, 176); g.lineTo(156, 176); g.stroke(); } }
      else if (expr === 'shout') { brow(60, 70, 100, 80); brow(196, 70, 156, 80); g.beginPath(); g.ellipse(128, 176, open ? 22 : 28, open ? 16 : 24, 0, 0, Math.PI * 2); g.fill(); }
      else if (open) talk(166, 18, 14);
      else { g.beginPath(); g.arc(128, 150, 26, 0.2 * Math.PI, 0.8 * Math.PI); g.stroke(); }
    }
  });
  faceCache.set(key, t);
  return t;
}

export function makeVillager(o = {}) {
  const c = { skin: '#f0c9a0', shirt: '#e0674f', pants: '#34495e', shoes: '#3a3a3a', hair: '#3b2a20', hairStyle: 'flat', expr: 'neutral', ...o };
  const root = new THREE.Group(); root.name = o.name || 'villager';
  const legs = {}, arms = {};
  for (const [n, s] of [['legL', -1], ['legR', 1]]) {
    const p = new THREE.Group(); at(p, s * 0.5, 2.0, 0);
    p.add(at(rbox(0.96, 1.72, 0.96, c.pants, 0.12), 0, -0.86, 0));
    p.add(at(rbox(1.0, 0.3, 1.1, c.shoes, 0.1), 0, -1.85, 0.05));
    root.add(p); legs[n] = p;
  }
  const torso = new THREE.Group(); at(torso, 0, 2.0, 0); root.add(torso);
  if (c.suit) {
    torso.add(at(rbox(2.0, 1.98, 1.0, c.suit, 0.12), 0, 1.0, 0));
    torso.add(at(rbox(0.62, 1.1, 0.05, '#f7f7f7', 0.03), 0, 1.42, 0.5));
    torso.add(at(rbox(0.2, 0.95, 0.06, c.tie || PAL.gold, 0.03), 0, 1.35, 0.53));
    if (c.chain) torso.add(at(rbox(0.75, 0.06, 0.05, PAL.gold, 0.02, { metalness: 0.8, roughness: 0.3 }), 0.45, 0.85, 0.53));
  } else {
    torso.add(at(rbox(2.0, 1.98, 1.0, c.shirt, 0.12), 0, 1.0, 0));
    if (c.apron) torso.add(at(rbox(1.5, 1.5, 0.05, c.apron, 0.03), 0, 0.75, 0.51));
  }
  if (c.coat) { torso.add(at(rbox(2.2, 3.1, 1.2, c.coat, 0.16), 0, 0.45, 0)); torso.add(at(rbox(2.3, 0.45, 1.3, c.collar || '#f2ece0', 0.18), 0, 1.95, 0)); for (let i = 0; i < 3; i++) torso.add(at(rbox(0.16, 0.16, 0.06, '#2b2b2b', 0.05), 0, 1.4 - i * 0.6, 0.62)); }
  if (c.shawl) torso.add(at(rbox(2.25, 0.9, 1.25, c.shawl, 0.2), 0, 1.75, 0));
  for (const [n, s] of [['armL', -1], ['armR', 1]]) {
    const p = new THREE.Group(); at(p, s * 1.48, 3.95, 0);
    p.add(at(rbox(c.coat ? 1.0 : 0.94, 1.55, c.coat ? 1.0 : 0.94, c.coat || c.suit || c.shirt, 0.12), 0, -0.78, 0));
    p.add(at(rbox(0.86, 0.45, 0.86, c.skin, 0.14), 0, -1.8, 0));
    root.add(p); arms[n] = p;
  }
  const head = new THREE.Group(); at(head, 0, 4.0, 0); root.add(head);
  head.add(at(rbox(1.3, 1.25, 1.25, c.skin, 0.26), 0, 0.68, 0));
  const face = plane(1.1, 1.1, faceTex(c.expr), { transparent: true }); face.castShadow = false;
  at(face, 0, 0.66, 0.632); head.add(face);
  const hs = c.hairStyle;
  if (hs === 'flat') head.add(at(rbox(1.38, 0.38, 1.36, c.hair, 0.14), 0, 1.35, -0.02));
  if (hs === 'puffy') { head.add(at(rbox(1.42, 0.52, 1.42, c.hair, 0.25), 0, 1.42, 0)); head.add(at(rbox(1.36, 0.12, 1.36, '#f5f5f0', 0.05), 0, 1.16, 0)); }
  if (hs === 'spiky') for (let i = -2; i <= 2; i++) head.add(at(rbox(0.32, 0.5, 1.1, c.hair, 0.08), i * 0.26, 1.42 + (i % 2 ? 0.05 : 0), -0.05));
  if (hs === 'long') { head.add(at(rbox(1.4, 0.38, 1.38, c.hair, 0.14), 0, 1.35, -0.02)); head.add(at(rbox(1.42, 1.0, 0.3, c.hair, 0.1), 0, 0.8, -0.58)); }
  if (hs === 'bald') { for (const s of [-1, 1]) head.add(at(rbox(0.18, 0.5, 0.9, c.hair, 0.06), s * 0.66, 0.85, -0.15)); head.add(at(rbox(1.2, 0.45, 0.2, c.hair, 0.06), 0, 0.85, -0.62)); }
  if (c.beard) { head.add(at(rbox(1.0, 0.3, 0.18, c.beard, 0.08), 0, 0.2, 0.6)); }
  if (c.mustache) head.add(at(rbox(0.6, 0.12, 0.1, c.mustache, 0.04), 0, 0.42, 0.66));
  if (c.cap) { head.add(at(rbox(1.38, 0.34, 1.38, c.cap, 0.16), 0, 1.38, 0)); head.add(at(rbox(1.2, 0.07, 0.6, c.cap, 0.03), 0, 1.24, 0.85)); }
  if (c.hood) {                                                                          // capuche relevee (ep06, Noe)
    head.add(at(rbox(1.52, 0.42, 1.5, c.hood, 0.2), 0, 1.4, -0.06));
    for (const s of [-1, 1]) head.add(at(rbox(0.16, 1.15, 1.36, c.hood, 0.08), s * 0.74, 0.78, -0.1));
    head.add(at(rbox(1.52, 1.2, 0.2, c.hood, 0.08), 0, 0.8, -0.72));
  }
  if (c.glasses) for (const s of [-1, 1]) head.add(at(rbox(0.36, 0.26, 0.04, c.glasses, 0.04, { roughness: 0.2 }), s * 0.32, 0.8, 0.64));
  root.userData.rig = { head, torso, ...arms, ...legs };
  root.userData.face = face;
  root.userData.expr = c.expr;
  root.userData.setExpr = (e) => { root.userData.expr = e; root.userData.setFace(''); };
  root.userData.setFace = (flags) => { const m = faceTex(flags ? root.userData.expr + '|' + flags : root.userData.expr); if (face.material.map !== m) { face.material.map = m; face.material.needsUpdate = true; } };
  return shadow(root);
}

export function makeBear(o = {}) {
  const c = { fur: '#5b3a29', belly: '#8a6448', ...o };
  const root = new THREE.Group(); root.name = 'bear';
  const legs = {}, arms = {};
  for (const [n, s] of [['legL', -1], ['legR', 1]]) {
    const p = new THREE.Group(); at(p, s * 1.05, 2.8, 0);
    p.add(at(rbox(1.7, 2.8, 1.8, c.fur, 0.35), 0, -1.4, 0));
    p.add(at(rbox(1.8, 0.4, 2.1, c.fur, 0.15), 0, -2.6, 0.2));
    root.add(p); legs[n] = p;
  }
  const torso = new THREE.Group(); at(torso, 0, 2.8, 0); root.add(torso);
  torso.add(at(rbox(4.2, 4.2, 2.9, c.fur, 0.6), 0, 2.1, 0));
  torso.add(at(rbox(2.6, 2.8, 0.2, c.belly, 0.3), 0, 1.9, 1.42));
  for (const [n, s] of [['armL', -1], ['armR', 1]]) {
    const p = new THREE.Group(); at(p, s * 2.7, 6.3, 0);
    p.add(at(rbox(1.35, 3.4, 1.4, c.fur, 0.35), 0, -1.6, 0));
    for (let i = -1; i <= 1; i++) { const cl = new THREE.Mesh(new THREE.ConeGeometry(0.13, 0.5, 6), mat('#f3efe6')); cl.rotation.x = Math.PI; at(cl, i * 0.38, -3.45, 0.5); p.add(cl); }
    root.add(p); arms[n] = p;
  }
  const head = new THREE.Group(); at(head, 0, 7.0, 0.1); root.add(head);
  head.add(at(rbox(3.0, 2.5, 2.6, c.fur, 0.55), 0, 1.25, 0));
  head.add(at(rbox(1.5, 1.0, 1.1, c.belly, 0.3), 0, 0.85, 1.4));
  head.add(at(rbox(0.6, 0.4, 0.3, '#1c1210', 0.12), 0, 1.2, 1.95));
  for (const s of [-1, 1]) {
    head.add(at(rbox(0.9, 0.9, 0.5, c.fur, 0.3), s * 1.25, 2.6, -0.2));
    head.add(at(rbox(0.5, 0.5, 0.2, c.belly, 0.15), s * 1.25, 2.6, 0.08));
    const eye = new THREE.Mesh(new THREE.SphereGeometry(0.22, 16, 12), new THREE.MeshStandardMaterial({ color: '#ff2a1a', emissive: '#ff2a1a', emissiveIntensity: 2.5 }));
    at(eye, s * 0.72, 1.75, 1.3); head.add(eye);
    const br = rbox(0.75, 0.16, 0.2, '#2a1a12', 0.06); br.rotation.z = s * -0.35; at(br, s * 0.72, 2.12, 1.32); head.add(br);
  }
  const jaw = new THREE.Group(); at(jaw, 0, 0.45, 1.0); head.add(jaw);
  jaw.add(at(rbox(1.3, 0.35, 0.9, c.belly, 0.12), 0, -0.1, 0.45));
  for (let i = -2; i <= 2; i++) { const t = new THREE.Mesh(new THREE.ConeGeometry(0.1, 0.3, 5), mat('#ffffff')); at(t, i * 0.24, 0.12, 0.85); jaw.add(t); }
  root.userData.rig = { head, torso, jaw, ...arms, ...legs };
  root.userData.eyes = [];
  head.traverse((m) => { if (m.isMesh && m.material.emissiveIntensity > 2) root.userData.eyes.push(m); });
  return shadow(root);
}

export function roofPrism(w, d, h, color, overhang = 0.35) {
  const s = new THREE.Shape(); s.moveTo(-w / 2 - overhang, 0); s.lineTo(w / 2 + overhang, 0); s.lineTo(0, h); s.closePath();
  const g = new THREE.ExtrudeGeometry(s, { depth: d + overhang * 2, bevelEnabled: true, bevelThickness: 0.08, bevelSize: 0.08, bevelSegments: 2 });
  g.translate(0, 0, -(d + overhang * 2) / 2);
  const m = new THREE.Mesh(g, mat(color, { roughness: 0.75 })); m.castShadow = true; m.receiveShadow = true;
  return m;
}

export function makeHouse(o = {}) {
  const c = { w: 6, d: 5, h: 4.2, floors: 1, wall: PAL.cream, roof: PAL.roofTerra, door: PAL.door, night: false, shutters: null, ...o };
  const g = new THREE.Group(); g.name = 'house';
  const H = c.h * c.floors;
  g.add(at(rbox(c.w, H, c.d, c.wall, 0.12), 0, H / 2, 0));
  const roof = roofPrism(c.w, c.d, c.w * 0.36, c.roof); at(roof, 0, H, 0); g.add(roof);
  const winMat = c.night ? mat(PAL.windowNight, { emissive: PAL.windowNight, emissiveIntensity: 1.4 }) : mat(PAL.windowDay, { roughness: 0.15, metalness: 0.1 });
  const windows = [];
  for (let f = 0; f < c.floors; f++) {
    const y = f * c.h + (f === 0 ? 2.3 : 2.4);
    const xs = f === 0 ? [-c.w * 0.3, c.w * 0.3] : [-c.w * 0.3, 0, c.w * 0.3];
    for (const x of xs) {
      if (f === 0 && Math.abs(x) < 0.01) continue;
      const wg = new THREE.Group(); at(wg, x, y, c.d / 2 + 0.02);
      wg.add(at(rbox(1.25, 1.35, 0.12, '#f7f3ea', 0.04), 0, 0, 0));
      const glass = at(rbox(1.0, 1.1, 0.06, winMat, 0.02), 0, 0, 0.05); wg.add(glass);
      wg.add(at(rbox(0.08, 1.1, 0.08, '#f7f3ea', 0.02), 0, 0, 0.08));
      if (c.shutters) for (const s of [-1, 1]) wg.add(at(rbox(0.45, 1.3, 0.08, c.shutters, 0.03), s * 0.88, 0, 0.02));
      g.add(wg); windows.push(wg);
    }
  }
  const doorPivot = new THREE.Group(); at(doorPivot, -0.6, 0, c.d / 2 + 0.04); g.add(doorPivot);
  doorPivot.add(at(rbox(1.2, 2.3, 0.14, c.door, 0.05), 0.6, 1.15, 0));
  const knob = new THREE.Mesh(new THREE.SphereGeometry(0.07, 10, 8), mat(PAL.gold, { metalness: 0.8, roughness: 0.3 })); at(knob, 1.0, 1.15, 0.1); doorPivot.add(knob);
  g.add(at(rbox(1.5, 2.5, 0.1, '#f7f3ea', 0.03), 0, 1.25, c.d / 2 + 0.01));
  const hole = new THREE.Mesh(new THREE.PlaneGeometry(1.2, 2.3), new THREE.MeshBasicMaterial({ color: '#17110c' }));
  at(hole, 0, 1.15, c.d / 2 + 0.065); g.add(hole);   // interieur sombre visible quand la porte s'ouvre
  g.add(at(rbox(1.9, 0.25, 0.9, '#a49a8c', 0.05), 0, 0.12, c.d / 2 + 0.45));
  g.userData = { door: doorPivot, windows, front: c.d / 2 };
  return shadow(g);
}

export function makeTownHall(o = {}) {
  const g = new THREE.Group(); g.name = 'townhall';
  const w = 14, d = 7, h = 8.5;
  g.add(at(rbox(w, h, d, PAL.stone, 0.15), 0, h / 2, 0));
  g.add(at(rbox(w + 0.5, 0.5, d + 0.5, '#c9c1b0', 0.1), 0, h + 0.2, 0));
  const roof = roofPrism(w, d, 3.2, PAL.roofSlate, 0.3); at(roof, 0, h + 0.45, 0); g.add(roof);
  const sign = plane(5.2, 1.1, textTex('MAIRIE', { w: 640, h: 136, bg: '#f2ece0', fg: '#2c2c2c', font: '900 96px Georgia, serif', border: '#3a3a3a' })); at(sign, 0, h - 1.3, d / 2 + 0.03); g.add(sign);
  for (const x of [-5, -2.6, 2.6, 5]) for (const y of [2.6, 5.6]) {
    const wg = new THREE.Group(); at(wg, x, y, d / 2 + 0.02);
    wg.add(at(rbox(1.3, 1.8, 0.1, '#ece6d8', 0.03), 0, 0, 0)); wg.add(at(rbox(1.05, 1.55, 0.06, '#2f4f7a', 0.02), 0, 0, 0.05));
    for (const s of [-1, 1]) wg.add(at(rbox(0.5, 1.75, 0.08, '#1f4a8a', 0.03), s * 0.95, 0, 0.03));
    g.add(wg);
  }
  g.add(at(rbox(2.0, 3.0, 0.15, '#2a2a2a', 0.05), 0, 1.5, d / 2 + 0.05));
  for (let i = 0; i < 3; i++) g.add(at(rbox(4.2 - i * 0.6, 0.3, 1.2 - i * 0.3, '#cfc7b6', 0.05), 0, 0.15 + i * 0.3, d / 2 + 0.9 - i * 0.15));
  const pole = rbox(0.08, 3.2, 0.08, '#6a6a6a', 0.03); at(pole, 4.2, h - 0.6, d / 2 + 0.6); pole.rotation.x = 0.6; g.add(pole);
  const flag = plane(1.5, 1.0, canvasTex(96, 64, (c) => { c.fillStyle = '#1f3f9a'; c.fillRect(0, 0, 32, 64); c.fillStyle = '#ffffff'; c.fillRect(32, 0, 32, 64); c.fillStyle = '#e03a3e'; c.fillRect(64, 0, 32, 64); }), { double: true });
  at(flag, 4.95, h + 0.5, d / 2 + 1.5); flag.rotation.x = 0.6; g.add(flag);
  return shadow(g);
}

export function makeStall(o = {}) {
  const c = { stripe: '#d94a3a', price: '-50%', ...o };
  const g = new THREE.Group(); g.name = 'stall';
  g.add(at(rbox(3.4, 0.25, 1.7, PAL.wood, 0.05), 0, 1.6, 0));
  g.add(at(rbox(3.3, 1.45, 1.6, PAL.woodDark, 0.05), 0, 0.75, 0));
  for (const x of [-1.6, 1.6]) for (const z of [-0.75, 0.75]) g.add(at(rbox(0.14, 3.6, 0.14, PAL.woodDark, 0.03), x, 1.8, z));
  const tex = canvasTex(256, 64, (cx) => { for (let i = 0; i < 8; i++) { cx.fillStyle = i % 2 ? '#fbf6ec' : c.stripe; cx.fillRect(i * 32, 0, 32, 64); } });
  const awn = new THREE.Mesh(new THREE.BoxGeometry(3.9, 0.12, 2.3), [mat('#fbf6ec'), mat('#fbf6ec'), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.8 }), mat('#fbf6ec'), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.8 }), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.8 })]);
  awn.rotation.x = 0.22; at(awn, 0, 3.65, 0.15); awn.castShadow = true; g.add(awn);
  const fruit = ['#e74c3c', '#f39c12', '#7ac943', '#f1c40f', '#c0392b'];
  for (let i = 0; i < 3; i++) {
    const crate = at(rbox(0.95, 0.45, 0.85, PAL.wood, 0.05), -1.05 + i * 1.05, 1.95, 0.1); g.add(crate);
    for (let j = 0; j < 6; j++) { const f = new THREE.Mesh(new THREE.SphereGeometry(0.15, 10, 8), mat(fruit[(i + j) % 5], { roughness: 0.4 })); at(f, -1.3 + i * 1.05 + (j % 3) * 0.25, 2.25, -0.1 + Math.floor(j / 3) * 0.3); f.castShadow = true; g.add(f); }
  }
  const signTex = canvasTex(256, 160, (cx, w, h) => { cx.fillStyle = PAL.yellow; cx.fillRect(0, 0, w, h); cx.strokeStyle = '#1b1b1b'; cx.lineWidth = 12; cx.strokeRect(6, 6, w - 12, h - 12); cx.fillStyle = '#d42b1e'; cx.font = '900 96px Montserrat, Arial Black, sans-serif'; cx.textAlign = 'center'; cx.textBaseline = 'middle'; cx.fillText(c.price, w / 2, h / 2 + 6); });
  const signG = new THREE.Group(); at(signG, 1.1, 2.0, 0.95); signG.rotation.y = -0.15;
  signG.add(at(rbox(0.08, 1.4, 0.08, PAL.woodDark, 0.02), 0, 0.7, 0));
  const sign = plane(1.3, 0.8, signTex, { double: true }); at(sign, 0, 1.6, 0.05); signG.add(sign);
  g.add(signG);
  g.userData = { sign: signG, signTex };
  return shadow(g);
}

export function makeTree(o = {}) {
  const g = new THREE.Group(); const s = o.scale || 1;
  g.add(at(rbox(0.6 * s, 2.6 * s, 0.6 * s, '#7a5236', 0.08), 0, 1.3 * s, 0));
  g.add(at(rbox(2.6 * s, 2.0 * s, 2.6 * s, o.leaf || '#5aa04a', 0.5 * s), 0, 3.4 * s, 0));
  g.add(at(rbox(1.8 * s, 1.4 * s, 1.8 * s, o.leaf2 || '#6db85a', 0.4 * s), 0.1 * s, 4.6 * s, 0.1 * s));
  return shadow(g);
}

export function makeLamp(night = false) {
  const g = new THREE.Group();
  g.add(at(rbox(0.16, 4.2, 0.16, '#2b2b2b', 0.04), 0, 2.1, 0));
  g.add(at(rbox(0.55, 0.7, 0.55, night ? '#ffe3a0' : '#f6f0de', 0.08, night ? { emissive: '#ffcf6b', emissiveIntensity: 1.6 } : {}), 0, 4.45, 0));
  g.add(at(rbox(0.7, 0.12, 0.7, '#2b2b2b', 0.04), 0, 4.85, 0));
  return shadow(g);
}

export function makeFountain() {
  const g = new THREE.Group();
  const cyl = (rt, rb, h, col, y) => { const m = new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, 28), mat(col)); at(m, 0, y, 0); m.castShadow = true; m.receiveShadow = true; g.add(m); return m; };
  cyl(3.2, 3.4, 0.9, '#d6cdbd', 0.45); cyl(2.85, 2.85, 0.2, '#7fc4e6', 0.82).material = mat('#7fc4e6', { roughness: 0.1, metalness: 0.1 });
  cyl(0.45, 0.6, 2.2, '#d6cdbd', 1.6); cyl(1.3, 0.9, 0.35, '#d6cdbd', 2.75); cyl(0.5, 0.5, 0.5, '#d6cdbd', 3.1);
  return g;
}

export function makeMountain(o = {}) {
  const g = new THREE.Group();
  const peak = (r, h, x, z, col) => {
    const m = new THREE.Mesh(new THREE.ConeGeometry(r, h, 7, 1), mat(col, { flatShading: true, roughness: 0.95 })); at(m, x, h / 2, z); g.add(m);
    const cap = new THREE.Mesh(new THREE.ConeGeometry(r * 0.32, h * 0.32, 7, 1), mat('#f4f7fb', { flatShading: true })); at(cap, x, h * 0.84 + 0.05, z); g.add(cap);
  };
  peak(34, 46, 0, 0, o.color || '#6f8a7a'); peak(24, 30, -36, 10, '#7f9888'); peak(26, 34, 38, 6, '#73907f');
  return g;
}

export function makeCastle() {
  const g = new THREE.Group();
  const hill = new THREE.Mesh(new THREE.SphereGeometry(20, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2), mat(PAL.grassDark)); hill.scale.set(1.4, 0.5, 1.0); g.add(hill);
  const base = 9.5;
  g.add(at(rbox(14, 7, 8, '#e8e1d2', 0.15), 0, base + 3.5, 0));
  for (const x of [-7.5, 7.5]) {
    const t = new THREE.Mesh(new THREE.CylinderGeometry(2.0, 2.2, 12, 16), mat('#efe9dc')); at(t, x, base + 6, 1); g.add(t);
    const r = new THREE.Mesh(new THREE.ConeGeometry(2.6, 4, 16), mat('#3d5a9a')); at(r, x, base + 14, 1); g.add(r);
    const fl = plane(1.4, 0.9, canvasTex(64, 40, (c) => { c.fillStyle = PAL.gold; c.fillRect(0, 0, 64, 40); }), { double: true }); at(fl, x + 0.8, base + 17.2, 1); g.add(fl);
    g.add(at(rbox(0.08, 2.2, 0.08, '#555', 0.03), x, base + 16.6, 1));
  }
  for (let i = -2; i <= 2; i++) g.add(at(rbox(1.0, 1.5, 0.15, PAL.windowNight, 0.04, { emissive: PAL.windowNight, emissiveIntensity: 0.7 }), i * 2.4, base + 4.2, 4.05));
  g.add(at(rbox(2.4, 3.4, 0.2, '#7a5236', 0.05), 0, base + 1.7, 4.1));
  return shadow(g);
}

export function makeGoldCar() {
  const g = new THREE.Group();
  const gold = { metalness: 0.85, roughness: 0.28 };
  g.add(at(rbox(4.6, 1.2, 2.3, PAL.gold, 0.35, gold), 0, 1.1, 0));
  g.add(at(rbox(2.6, 1.0, 2.0, PAL.gold, 0.35, gold), -0.3, 2.05, 0));
  g.add(at(rbox(2.4, 0.8, 2.05, '#26324a', 0.25, { roughness: 0.15 }), -0.3, 2.05, 0));
  for (const x of [-1.5, 1.5]) for (const z of [-1.15, 1.15]) { const w = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.55, 0.4, 20), mat('#1d1d1d')); w.rotation.x = Math.PI / 2; at(w, x, 0.55, z); g.add(w); }
  for (const z of [-0.7, 0.7]) g.add(at(rbox(0.1, 0.3, 0.45, '#fff8d0', 0.05, { emissive: '#fff3b0', emissiveIntensity: 1 }), 2.3, 1.25, z));
  return shadow(g);
}

export function makePassCard() {
  const tex = canvasTex(512, 320, (c, w, h) => {
    const gr = c.createLinearGradient(0, 0, w, h); gr.addColorStop(0, '#ffe680'); gr.addColorStop(0.5, '#f1c40f'); gr.addColorStop(1, '#c99a06');
    c.fillStyle = gr; c.fillRect(0, 0, w, h); c.strokeStyle = '#8a6a00'; c.lineWidth = 14; c.strokeRect(7, 7, w - 14, h - 14);
    c.fillStyle = '#3a2a00'; c.font = '900 64px Montserrat, Arial Black, sans-serif'; c.textAlign = 'center'; c.fillText('PASS', w / 2, 120); c.fillText('BROKER', w / 2, 200);
    c.fillStyle = '#d9b23a'; c.fillRect(48, 232, 90, 60); c.strokeStyle = '#8a6a00'; c.lineWidth = 4; c.strokeRect(48, 232, 90, 60);
  });
  const g = new THREE.Group();
  const card = new THREE.Mesh(new THREE.BoxGeometry(1.6, 1.0, 0.05), [mat(PAL.gold), mat(PAL.gold), mat(PAL.gold), mat(PAL.gold), new THREE.MeshStandardMaterial({ map: tex, metalness: 0.5, roughness: 0.3, emissive: '#fff2b0', emissiveMap: tex, emissiveIntensity: 0.35 }), mat(PAL.gold)]);
  card.castShadow = true; g.add(card);
  return g;
}

export function makeGate() {
  const g = new THREE.Group();
  for (const s of [-1, 1]) g.add(at(rbox(1.2, 7, 1.2, '#cfc6b3', 0.1), s * 4.2, 3.5, 0));
  g.add(at(rbox(9.8, 1.3, 1.4, '#cfc6b3', 0.1), 0, 7.4, 0));
  const sign = plane(6, 1.1, textTex('MARCHÉ', { w: 640, h: 120, bg: '#1f3f6a', fg: PAL.gold, font: '900 92px Montserrat, Arial Black, sans-serif' })); at(sign, 0, 7.4, 0.72); g.add(sign);
  const doors = [];
  for (const s of [-1, 1]) {
    const p = new THREE.Group(); at(p, s * 3.6, 0, 0); g.add(p);
    for (let i = 0; i < 5; i++) p.add(at(rbox(0.14, 5.8, 0.14, '#3a3a3a', 0.04, { metalness: 0.6, roughness: 0.4 }), -s * (0.35 + i * 0.7), 2.9, 0));
    p.add(at(rbox(3.6, 0.16, 0.16, '#3a3a3a', 0.04, { metalness: 0.6 }), -s * 1.8, 5.6, 0));
    p.add(at(rbox(3.6, 0.16, 0.16, '#3a3a3a', 0.04, { metalness: 0.6 }), -s * 1.8, 0.6, 0));
    doors.push(p);
  }
  g.userData = { doors };
  return shadow(g);
}

export function makeCoin() {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.32, 0.08, 24), mat(PAL.gold, { metalness: 0.9, roughness: 0.25, emissive: '#7a5a00', emissiveIntensity: 0.25 }));
  m.rotation.x = Math.PI / 2; m.castShadow = true; return m;
}

export function makeTicker(o = {}) {
  const c = { title: 'S&P 500', value: '-4,4 %', sub: '5 nov. 2026', ...o };
  const tex = canvasTex(1024, 640, () => {});
  const drawChart = (p) => {
    const g = tex.userData.ctx, w = 1024, h = 640;
    g.fillStyle = '#0f1724'; g.fillRect(0, 0, w, h);
    g.strokeStyle = 'rgba(255,255,255,0.08)'; g.lineWidth = 2;
    for (let x = 80; x < w; x += 80) { g.beginPath(); g.moveTo(x, 150); g.lineTo(x, h - 40); g.stroke(); }
    for (let y = 150; y < h; y += 70) { g.beginPath(); g.moveTo(40, y); g.lineTo(w - 40, y); g.stroke(); }
    g.font = '900 64px Montserrat, Arial Black, sans-serif'; g.fillStyle = '#ffffff'; g.textAlign = 'left'; g.fillText(c.title, 50, 95);
    g.textAlign = 'right'; g.fillStyle = PAL.loss; g.fillText(c.value, w - 50, 95);
    g.font = '700 30px Montserrat, Arial, sans-serif'; g.fillStyle = '#9fb0c8'; g.fillText(c.sub, w - 50, 132);
    const pts = []; const N = 60;
    for (let i = 0; i <= N; i++) { const x = 60 + (i / N) * (w - 120); const base = i < N * 0.72 ? 250 + Math.sin(i * 0.7) * 22 - i * 1.2 : 200 + Math.pow(i - N * 0.72, 1.35) * 14 + Math.sin(i * 1.3) * 8; pts.push([x, base]); }
    const n = Math.max(2, Math.floor(p * N));
    g.strokeStyle = n > N * 0.72 ? PAL.loss : '#7fd1a8'; g.lineWidth = 9; g.lineJoin = 'round'; g.beginPath();
    pts.slice(0, n + 1).forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y))); g.stroke();
    const [lx, ly] = pts[Math.min(n, N)]; g.fillStyle = '#ffffff'; g.beginPath(); g.arc(lx, ly, 12, 0, Math.PI * 2); g.fill();
    tex.needsUpdate = true;
  };
  drawChart(1);
  const g = new THREE.Group();
  g.add(at(rbox(10.6, 6.9, 0.5, '#20242c', 0.12), 0, 0, -0.2));
  const scr = plane(10, 6.25, tex, { emissive: 0.9 }); at(scr, 0, 0, 0.07); g.add(scr);
  g.add(at(rbox(0.4, 6, 0.4, '#20242c', 0.06), -3.5, -5.5, -0.2)); g.add(at(rbox(0.4, 6, 0.4, '#20242c', 0.06), 3.5, -5.5, -0.2));
  g.userData = { drawChart };
  return shadow(g);
}

export function makePriceBoard() {
  const tex = canvasTex(512, 512, () => {});
  const draw = (val, arrow) => {
    const g = tex.userData.ctx;
    g.fillStyle = '#f6eedc'; g.fillRect(0, 0, 512, 512); g.strokeStyle = '#3b2a1c'; g.lineWidth = 22; g.strokeRect(11, 11, 490, 490);
    g.fillStyle = '#3b2a1c'; g.font = '900 54px Montserrat, Arial Black, sans-serif'; g.textAlign = 'center'; g.fillText('PRIX DU JOUR', 256, 92);
    g.font = '900 210px Montserrat, Arial Black, sans-serif';
    const tw = g.measureText(val).width; if (tw > 440) g.font = `900 ${Math.floor(210 * 440 / tw)}px Montserrat, Arial Black, sans-serif`;
    g.fillStyle = arrow ? PAL.loss : '#2b2b2b'; g.fillText(val, 256, 330);
    if (arrow) { g.fillStyle = PAL.loss; g.beginPath(); g.moveTo(206, 380); g.lineTo(306, 380); g.lineTo(306, 420); g.lineTo(350, 420); g.lineTo(256, 490); g.lineTo(162, 420); g.lineTo(206, 420); g.closePath(); g.fill(); }
    tex.needsUpdate = true;
  };
  draw('100 €', false);
  const g = new THREE.Group();
  g.add(at(rbox(4.6, 4.6, 0.3, PAL.woodDark, 0.08), 0, 0, -0.18));
  const p = plane(4.2, 4.2, tex); at(p, 0, 0, 0.0); g.add(p);
  g.userData = { draw };
  return shadow(g);
}

export function makeSubscribe() {
  const tex = canvasTex(1024, 300, (c, w, h) => {
    c.clearRect(0, 0, w, h);
    const r = 140; c.fillStyle = '#e8202a'; c.beginPath(); c.roundRect(20, 20, w - 40, h - 40, r); c.fill();
    c.fillStyle = '#ffffff'; c.font = '900 110px Montserrat, Arial Black, sans-serif'; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText('ABONNE-TOI', w / 2 + 40, h / 2 + 6);
    c.save(); c.translate(130, h / 2); c.fillStyle = '#ffffff'; c.beginPath(); c.moveTo(-34, 30); c.quadraticCurveTo(-34, -45, 0, -48); c.quadraticCurveTo(34, -45, 34, 30); c.lineTo(46, 42); c.lineTo(-46, 42); c.closePath(); c.fill(); c.beginPath(); c.arc(0, 54, 12, 0, Math.PI * 2); c.fill(); c.restore();
  });
  const m = plane(5.2, 1.52, tex, { transparent: true, emissive: 0.6 }); m.castShadow = false; m.material.depthTest = false; m.renderOrder = 999;
  return m;
}

export function makeSky(top, horizon) {
  const geo = new THREE.SphereGeometry(400, 32, 16);
  const m = new THREE.ShaderMaterial({ side: THREE.BackSide, depthWrite: false, fog: false,
    uniforms: { top: { value: new THREE.Color(top) }, hor: { value: new THREE.Color(horizon) } },
    vertexShader: 'varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0);}',
    fragmentShader: 'uniform vec3 top; uniform vec3 hor; varying vec3 vP; void main(){ float t = clamp(vP.y*1.6+0.05,0.0,1.0); gl_FragColor = vec4(mix(hor, top, t),1.0);\n#include <colorspace_fragment>\n}' });
  const s = new THREE.Mesh(geo, m); s.name = 'sky'; s.renderOrder = -1;
  return s;
}

export function makeGround(o = {}) {
  const g = new THREE.Group();
  const grass = new THREE.Mesh(new THREE.PlaneGeometry(600, 600), mat(o.grass || PAL.grass, { roughness: 1 }));
  grass.rotation.x = -Math.PI / 2; grass.receiveShadow = true; g.add(grass);
  const cobTex = canvasTex(512, 512, (c, w, h) => {
    c.fillStyle = o.cobble || PAL.cobble; c.fillRect(0, 0, w, h);
    for (let y = 0; y < 16; y++) for (let x = 0; x < 16; x++) {
      const v = ((x * 73 + y * 151) % 17) / 17; c.fillStyle = `rgba(90,75,55,${0.06 + v * 0.08})`;
      c.beginPath(); c.roundRect(x * 32 + (y % 2) * 16 + 2, y * 32 + 2, 28, 28, 7); c.fill();
    }
  });
  cobTex.wrapS = cobTex.wrapT = THREE.RepeatWrapping; cobTex.repeat.set(8, 8);
  const sq = new THREE.Mesh(new THREE.PlaneGeometry(64, 64), new THREE.MeshStandardMaterial({ map: cobTex, roughness: 0.95 }));
  sq.rotation.x = -Math.PI / 2; sq.position.y = 0.02; sq.receiveShadow = true; g.add(sq);
  return g;
}

// ---------- Ajouts ep02 (inflation) : banque a horloge, moulin, champ, chambre de Lea, atelier de frappe ----------
export function makeBank(o = {}) {
  const c = { pct: '-3 %', ...o };
  const g = new THREE.Group(); g.name = 'bank';
  const w = 16, d = 8, h = 8;
  g.add(at(rbox(w, h, d, '#e6dfcf', 0.12), 0, h / 2, 0));
  for (let i = 0; i < 3; i++) g.add(at(rbox(w + 2 - i * 0.6, 0.35, d + 3 - i * 0.8, '#cfc6b3', 0.05), 0, 0.17 + i * 0.35, 1.2 - i * 0.3));
  for (const x of [-6, -3.2, 3.2, 6]) {
    const col = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.6, h - 1.2, 16), mat('#f3eee3')); at(col, x, (h - 1.2) / 2 + 1.05, d / 2 + 1.2); col.castShadow = true; g.add(col);
  }
  g.add(at(rbox(w + 1, 0.7, d + 3, '#d8d0be', 0.08), 0, h + 0.1, 1.0));
  const ped = roofPrism(w + 0.4, d + 2.6, 2.6, '#d8d0be', 0.2); at(ped, 0, h + 0.45, 1.0); g.add(ped);
  const sign = plane(7.5, 1.3, textTex('BANQUE', { w: 760, h: 136, bg: '#2a3b5c', fg: PAL.gold, font: '900 104px Georgia, serif' })); at(sign, 0, h - 0.9, d / 2 + 2.53); g.add(sign);
  const winMat = mat('#2f4f7a', { roughness: 0.2 });
  const windows = [];
  for (const x of [-5.2, 5.2]) for (const y of [2.8, 5.6]) { const m = at(rbox(1.5, 1.9, 0.1, winMat, 0.03), x, y, d / 2 + 0.05); g.add(m); windows.push(m); }
  const doors = [];
  for (const s of [-1, 1]) {
    const p = new THREE.Group(); at(p, s * 1.6, 0, d / 2 + 0.08); g.add(p);
    p.add(at(rbox(1.6, 4.2, 0.18, '#5a3a22', 0.05), -s * 0.8, 2.1 + 1.05, 0));
    p.add(at(rbox(0.5, 0.5, 0.05, PAL.gold, 0.03, { metalness: 0.8, roughness: 0.3 }), -s * 0.8, 3.4, 0.12));
    doors.push(p);
  }
  const inner = new THREE.Mesh(new THREE.PlaneGeometry(3.2, 4.2), new THREE.MeshStandardMaterial({ color: '#ffcf6b', emissive: '#ffb347', emissiveIntensity: 0 }));
  at(inner, 0, 3.15, d / 2 + 0.03); g.add(inner);
  // tour de l'horloge
  const tower = new THREE.Group(); at(tower, 0, h + 2.6, -0.5); g.add(tower);
  tower.add(at(rbox(4.2, 4.6, 4.2, '#e6dfcf', 0.1), 0, 2.3, 0));
  const troof = roofPrism(4.2, 4.2, 2.2, PAL.roofSlate, 0.25); at(troof, 0, 4.6, 0); tower.add(troof);
  const clockTex = canvasTex(512, 512, () => {});
  const drawClock = (ang = 0, pctTxt = c.pct, glow = false) => {
    const x = clockTex.userData.ctx, R = 236;
    x.clearRect(0, 0, 512, 512);
    x.fillStyle = glow ? '#fff2c0' : '#f6efdc'; x.beginPath(); x.arc(256, 256, R, 0, Math.PI * 2); x.fill();
    x.lineWidth = 18; x.strokeStyle = '#3b2a1c'; x.stroke();
    x.fillStyle = '#3b2a1c'; for (let i = 0; i < 12; i++) { const a = i / 12 * Math.PI * 2; x.fillRect(256 + Math.sin(a) * 200 - 6, 256 - Math.cos(a) * 200 - 14, 12, 28); }
    x.fillStyle = PAL.loss; x.font = '900 92px Montserrat, Arial Black, sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle'; x.fillText(pctTxt, 256, 360);
    x.strokeStyle = '#1b1b1b'; x.lineCap = 'round';
    x.lineWidth = 16; x.beginPath(); x.moveTo(256, 256); x.lineTo(256 + Math.sin(ang / 12) * 110, 256 - Math.cos(ang / 12) * 110); x.stroke();
    x.lineWidth = 10; x.beginPath(); x.moveTo(256, 256); x.lineTo(256 + Math.sin(ang) * 170, 256 - Math.cos(ang) * 170); x.stroke();
    x.fillStyle = '#1b1b1b'; x.beginPath(); x.arc(256, 256, 16, 0, Math.PI * 2); x.fill();
    clockTex.needsUpdate = true;
  };
  drawClock(0);
  const clock = plane(3.4, 3.4, clockTex, { transparent: true, emissive: 0.25 }); at(clock, 0, 2.4, 2.13); tower.add(clock);
  // cheminee + fumee
  const chim = at(rbox(1.1, 3.2, 1.1, '#9a5a44', 0.06), 5.5, h + 2.2, -2); g.add(chim);
  const smoke = [];
  for (let i = 0; i < 7; i++) { const s = new THREE.Mesh(new THREE.SphereGeometry(0.7, 10, 8), new THREE.MeshStandardMaterial({ color: '#8f8f96', transparent: true, opacity: 0.5, roughness: 1, depthWrite: false })); at(s, 5.5, h + 4, -2); g.add(s); smoke.push(s); }
  const tickSmoke = (t, on = true) => smoke.forEach((s, i) => {
    const k = ((t * 0.35 + i / smoke.length) % 1);
    s.visible = on; s.position.set(5.5 + k * 2.2 + Math.sin(t + i) * 0.3, h + 4 + k * 7, -2 - k * 0.6); s.scale.setScalar(0.6 + k * 1.6); s.material.opacity = 0.55 * (1 - k);
  });
  g.userData = { doors, inner, windows, winMat, clock, drawClock, tickSmoke, front: d / 2 + 2.5, clockPos: [0, h + 5.0, 1.63] };
  return shadow(g);
}

export function makeMill() {
  const g = new THREE.Group(); g.name = 'mill';
  const tower = new THREE.Mesh(new THREE.CylinderGeometry(2.6, 3.4, 9, 12), mat('#e3d6bd', { flatShading: true })); at(tower, 0, 4.5, 0); g.add(tower);
  const roof = new THREE.Mesh(new THREE.ConeGeometry(3.3, 3.2, 12), mat(PAL.roofBrown, { flatShading: true })); at(roof, 0, 10.6, 0); g.add(roof);
  g.add(at(rbox(1.5, 2.5, 0.3, PAL.woodDark, 0.05), 0, 1.25, 3.15));
  g.add(at(rbox(1.0, 1.0, 0.2, '#f6e2a8', 0.04), 0, 5.4, 2.85));
  const hub = new THREE.Group(); at(hub, 0, 8.6, 3.0); g.add(hub);
  hub.add(at(rbox(0.7, 0.7, 0.8, PAL.woodDark, 0.1), 0, 0, 0));
  for (let i = 0; i < 4; i++) {
    const arm = new THREE.Group(); arm.rotation.z = i * Math.PI / 2; hub.add(arm);
    arm.add(at(rbox(0.25, 5.0, 0.15, PAL.woodDark, 0.03), 0, 2.5, 0.3));
    arm.add(at(rbox(1.4, 3.8, 0.08, '#f4efe3', 0.02), 0.8, 3.0, 0.32));
  }
  const sacks = new THREE.Group(); at(sacks, 3.6, 0, 2.6); g.add(sacks);
  for (const [x, z, y] of [[0, 0, 0], [1.1, 0.2, 0], [0.5, 0.1, 1.0]]) {
    const s = at(rbox(1.0, 1.1, 0.8, '#ead9b5', 0.3), x, 0.55 + y, z); sacks.add(s);
    sacks.add(at(rbox(0.5, 0.15, 0.5, '#a8895a', 0.05), x, 1.15 + y, z));
  }
  g.userData = { blades: hub, sacks };
  return shadow(g);
}

export function makeField(o = {}) {
  const c = { w: 22, d: 14, rows: 8, per: 16, ...o };
  const g = new THREE.Group(); g.name = 'field';
  const soil = at(rbox(c.w, 0.3, c.d, '#7a5236', 0.05), 0, 0.1, 0); g.add(soil);
  for (let r = 0; r < c.rows; r++) g.add(at(rbox(c.w - 0.6, 0.3, 0.7, '#5e3d26', 0.1), 0, 0.3, -c.d / 2 + 1 + r * (c.d - 2) / (c.rows - 1)));
  const stalkGeo = new THREE.BoxGeometry(0.22, 1, 0.22); stalkGeo.translate(0, 0.5, 0);
  const headGeo = new THREE.BoxGeometry(0.34, 0.5, 0.34); headGeo.translate(0, 1.15, 0);
  const stalkMat = mat('#8fbf4f'), headMat = mat('#e8c35a');
  const N = c.rows * c.per;
  const stalks = new THREE.InstancedMesh(stalkGeo, stalkMat, N), heads = new THREE.InstancedMesh(headGeo, headMat, N);
  stalks.castShadow = heads.castShadow = true; g.add(stalks); g.add(heads);
  const pos = [];
  for (let r = 0; r < c.rows; r++) for (let i = 0; i < c.per; i++) pos.push([-c.w / 2 + 1 + i * (c.w - 2) / (c.per - 1) + Math.sin(r * 3 + i) * 0.15, -c.d / 2 + 1 + r * (c.d - 2) / (c.rows - 1)]);
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler();
  const grow = (k, t = 0, ripe = 0) => {
    for (let i = 0; i < N; i++) {
      const [x, z] = pos[i]; const kk = Math.max(0.001, Math.min(1, k * 1.2 - (i % 7) * 0.03));
      e.set(Math.sin(t * 1.6 + x * 0.4) * 0.08, 0, Math.sin(t * 1.3 + z * 0.5) * 0.08); q.setFromEuler(e);
      m4.compose(new THREE.Vector3(x, 0.4, z), q, new THREE.Vector3(1, kk * 2.6, 1)); stalks.setMatrixAt(i, m4);
      m4.compose(new THREE.Vector3(x, 0.4, z), q, new THREE.Vector3(kk, kk * 2.6, kk)); heads.setMatrixAt(i, m4);
    }
    stalks.instanceMatrix.needsUpdate = heads.instanceMatrix.needsUpdate = true;
    stalkMat.color.set(ripe > 0.5 ? '#d9b44a' : '#8fbf4f'); heads.visible = ripe > 0 || k > 0.6;
  };
  grow(0);
  const fence = new THREE.Group(); g.add(fence);
  for (let i = 0; i <= 11; i++) fence.add(at(rbox(0.25, 1.4, 0.25, PAL.wood, 0.04), -c.w / 2 - 0.6 + i * (c.w + 1.2) / 11, 0.7, c.d / 2 + 0.8));
  fence.add(at(rbox(c.w + 1.4, 0.18, 0.12, PAL.wood, 0.03), 0, 1.0, c.d / 2 + 0.8));
  g.userData = { grow, w: c.w, d: c.d };
  return shadow(g);
}

export function makeBedroom() {
  const g = new THREE.Group(); g.name = 'bedroom';
  const floorTex = canvasTex(256, 256, (x, w, h) => { for (let i = 0; i < 8; i++) { x.fillStyle = i % 2 ? '#a87a50' : '#b98a5e'; x.fillRect(0, i * 32, w, 32); x.fillStyle = 'rgba(0,0,0,0.12)'; x.fillRect(0, i * 32, w, 2); } });
  floorTex.wrapS = floorTex.wrapT = THREE.RepeatWrapping; floorTex.repeat.set(3, 3);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(16, 16), new THREE.MeshStandardMaterial({ map: floorTex, roughness: 0.9 })); floor.rotation.x = -Math.PI / 2; floor.position.y = 0.03; floor.receiveShadow = true; g.add(floor);
  g.add(at(rbox(16, 8, 0.4, '#d9c6a5', 0.05), 0, 4, -8));
  g.add(at(rbox(0.4, 8, 16, '#cdb994', 0.05), -8, 4, 0));
  g.add(at(rbox(16, 0.5, 0.5, '#8a6440', 0.05), 0, 0.25, -7.7));
  const win = new THREE.Group(); at(win, 2.5, 4.8, -7.75); g.add(win);
  win.add(at(rbox(3.0, 2.6, 0.2, '#f2ead8', 0.04), 0, 0, 0));
  win.add(at(rbox(2.6, 2.2, 0.1, '#1a2a55', 0.02, { emissive: '#22356e', emissiveIntensity: 0.6 }), 0, 0, 0.08));
  const moon = new THREE.Mesh(new THREE.CircleGeometry(0.35, 20), new THREE.MeshBasicMaterial({ color: '#fff6d0' })); at(moon, 0.7, 0.5, 0.15); win.add(moon);
  win.add(at(rbox(0.1, 2.2, 0.12, '#f2ead8', 0.02), 0, 0, 0.12)); win.add(at(rbox(2.6, 0.1, 0.12, '#f2ead8', 0.02), 0, 0, 0.12));
  const bed = new THREE.Group(); at(bed, -3.5, 0, -3.5); g.add(bed);
  bed.add(at(rbox(4.2, 0.9, 6.6, '#7a5236', 0.08), 0, 0.45, 0));
  bed.add(at(rbox(4.2, 2.6, 0.4, '#6a4428', 0.08), 0, 1.3, -3.2));
  bed.add(at(rbox(3.9, 0.15, 6.2, '#e9dfc8', 0.03), 0, 0.98, 0.1));
  const matPivot = new THREE.Group(); at(matPivot, -2.0, 1.05, 0.1); bed.add(matPivot);
  matPivot.add(at(rbox(3.9, 0.6, 6.2, '#f4f1ea', 0.25), 1.95, 0.3, 0));
  matPivot.add(at(rbox(3.95, 0.25, 4.0, '#4f7fb8', 0.1), 1.95, 0.66, 1.0));
  matPivot.add(at(rbox(2.4, 0.5, 1.2, '#ffffff', 0.25), 1.95, 0.85, -2.3));
  const coins = new THREE.Group(); at(coins, 0, 1.1, 0.2); bed.add(coins);
  for (let i = 0; i < 10; i++) { const cn = makeCoin(); cn.rotation.x = 0; cn.material = cn.material.clone(); cn.material.emissive.set('#b8860b'); cn.material.emissiveIntensity = 0.7; at(cn, -0.9 + (i % 5) * 0.45, 0.04 + Math.floor(i / 5) * 0.09, -0.3 + Math.floor(i / 5) * 0.55); coins.add(cn); }
  const table = new THREE.Group(); at(table, 0.6, 0, -6.2); g.add(table);
  table.add(at(rbox(1.4, 1.4, 1.2, '#8a6440', 0.06), 0, 0.7, 0));
  table.add(at(rbox(0.3, 0.6, 0.3, '#f6f0de', 0.05), 0, 1.7, 0));
  const flame = at(rbox(0.14, 0.24, 0.14, '#ffcf6b', 0.06, { emissive: '#ffb347', emissiveIntensity: 2.2 }), 0, 2.12, 0); table.add(flame);
  g.userData = { mattress: matPivot, coins, flame, bed, candle: [0.6, 2.4, -6.2] };
  return shadow(g);
}

export function makeCoinPress() {
  const g = new THREE.Group(); g.name = 'coinpress';
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(18, 18), mat('#6f665a', { roughness: 1 })); floor.rotation.x = -Math.PI / 2; floor.position.y = 0.03; floor.receiveShadow = true; g.add(floor);
  const wallTex = canvasTex(256, 256, (x, w, h) => { x.fillStyle = '#7d756a'; x.fillRect(0, 0, w, h); for (let r = 0; r < 8; r++) for (let i = 0; i < 4; i++) { x.fillStyle = `rgba(0,0,0,${0.08 + ((r * 3 + i) % 4) * 0.03})`; x.fillRect(i * 64 + (r % 2) * 32 + 2, r * 32 + 2, 60, 28); } });
  wallTex.wrapS = wallTex.wrapT = THREE.RepeatWrapping; wallTex.repeat.set(4, 2);
  const wall = new THREE.Mesh(new THREE.BoxGeometry(18, 9, 0.5), new THREE.MeshStandardMaterial({ map: wallTex, roughness: 1 })); at(wall, 0, 4.5, -7); wall.receiveShadow = true; g.add(wall);
  const press = new THREE.Group(); at(press, 0, 0, -3); g.add(press);
  press.add(at(rbox(3.6, 1.6, 2.4, '#3a3a40', 0.1, { metalness: 0.6, roughness: 0.4 }), 0, 0.8, 0));
  for (const s of [-1, 1]) press.add(at(rbox(0.5, 6.2, 0.6, '#3a3a40', 0.06, { metalness: 0.6, roughness: 0.4 }), s * 1.5, 3.1, 0));
  press.add(at(rbox(4.0, 0.8, 1.0, '#2a2a30', 0.08, { metalness: 0.6 }), 0, 6.3, 0));
  const ram = new THREE.Group(); at(ram, 0, 3.6, 0); press.add(ram);
  ram.add(at(rbox(0.6, 2.4, 0.6, '#8a8a92', 0.05, { metalness: 0.8, roughness: 0.3 }), 0, 1.2, 0));
  ram.add(at(rbox(1.6, 0.5, 1.4, '#2a2a30', 0.06, { metalness: 0.6 }), 0, 0, 0));
  const wheel = new THREE.Mesh(new THREE.TorusGeometry(1.3, 0.12, 8, 24), mat('#7a5236')); at(wheel, 0, 7.2, 0); press.add(wheel);
  const pile = new THREE.Group(); at(pile, 3.6, 0, -1.2); g.add(pile);
  const cGeo = new THREE.CylinderGeometry(0.32, 0.32, 0.08, 16);
  const cMat = new THREE.MeshStandardMaterial({ color: PAL.gold, metalness: 0.9, roughness: 0.25, emissive: '#b8860b', emissiveIntensity: 0.5 });
  const NP = 260; const pileMesh = new THREE.InstancedMesh(cGeo, cMat, NP); pileMesh.castShadow = true; pile.add(pileMesh);
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler();
  const fillPile = (k) => {
    const n = Math.floor(NP * k); pileMesh.count = n;
    for (let i = 0; i < n; i++) {
      const a = i * 2.399, r = Math.sqrt(i / NP) * 2.4, y = Math.max(0.05, (1 - r / 2.4) * 1.8 * Math.min(1, k * 1.4)) + (i % 3) * 0.03;
      e.set(Math.sin(i) * 0.4, i, Math.cos(i * 1.7) * 0.4); q.setFromEuler(e); m4.compose(new THREE.Vector3(Math.cos(a) * r, y, Math.sin(a) * r), q, new THREE.Vector3(1, 1, 1)); pileMesh.setMatrixAt(i, m4);
    }
    pileMesh.instanceMatrix.needsUpdate = true;
  };
  fillPile(0.4);
  const furnace = new THREE.Group(); at(furnace, -5, 0, -5.4); g.add(furnace);
  furnace.add(at(rbox(3.2, 3.4, 2.4, '#8a4a36', 0.1), 0, 1.7, 0));
  furnace.add(at(rbox(1.6, 1.2, 0.1, '#ff8a2a', 0.04, { emissive: '#ff6a00', emissiveIntensity: 2.4 }), 0, 1.4, 1.22));
  g.userData = { ram, fillPile, wheel, glow: [-5, 2, -3.5] };
  return shadow(g);
}

// ---------- Ajouts ep03 (faux rabais) : boutique a vitrine + etiquettes, tirelire, carnet, pile d'assiettes, bonnet ----------
function tagTex(mode) {
  // mode 'promo' : 100 barre + 40 ; 'old' : vieille etiquette jaunie "40"
  return canvasTex(256, 320, (g, w, h) => {
    if (mode === 'old') {
      g.fillStyle = '#e8d49a'; g.fillRect(0, 0, w, h); g.fillStyle = 'rgba(120,90,30,0.25)'; for (let i = 0; i < 40; i++) g.fillRect((i * 53) % w, (i * 97) % h, 9, 6);
      g.strokeStyle = '#8a6a30'; g.lineWidth = 10; g.strokeRect(5, 5, w - 10, h - 10);
      g.fillStyle = '#3b2a12'; g.font = '900 150px Montserrat, Arial Black, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText('40', w / 2, h / 2 + 8);
      g.font = '700 30px Montserrat, Arial, sans-serif'; g.fillText('pièces', w / 2, h - 45);
      return;
    }
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, w, h); g.strokeStyle = '#d42b1e'; g.lineWidth = 12; g.strokeRect(6, 6, w - 12, h - 12);
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillStyle = '#444'; g.font = '900 92px Montserrat, Arial Black, sans-serif'; g.fillText('100', w / 2, 82);
    g.strokeStyle = '#d42b1e'; g.lineWidth = 12; g.beginPath(); g.moveTo(40, 108); g.lineTo(w - 40, 56); g.stroke();
    g.fillStyle = '#d42b1e'; g.font = '900 140px Montserrat, Arial Black, sans-serif'; g.fillText('40', w / 2, 210);
    g.font = '900 40px Montserrat, Arial Black, sans-serif'; g.fillText('-60 %', w / 2, 288);
  });
}

export function makeShop() {
  const g = new THREE.Group(); g.name = 'shop';
  g.add(at(rbox(16, 9, 5, '#7b2f3a', 0.1), 0, 4.5, -4.6));
  for (const [x, y, ww, hh] of [[-7.6, 4.5, 0.8, 9], [5.6, 4.5, 4.8, 9], [-2, 8.1, 10.4, 1.8], [-2, 0.5, 10.4, 1.0]]) g.add(at(rbox(ww, hh, 0.6, '#7b2f3a', 0.06), x, y, -0.3));
  for (const x of [-7.15, 3.15]) g.add(at(rbox(0.3, 6.2, 1.6, '#5a2a30', 0.04), x, 4.1, -1.35));
  g.add(at(rbox(17, 1.0, 6, '#3b1f24', 0.1), 0, 9.3, -2.3));
  const sign = plane(11, 1.9, canvasTex(1024, 180, (c, w, h) => { c.fillStyle = '#1b1b1b'; c.fillRect(0, 0, w, h); c.fillStyle = PAL.yellow; c.font = '900 110px Montserrat, Arial Black, sans-serif'; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText('VENDREDI NOIR', w / 2, h / 2 + 6); }), { emissive: 0.5 });
  at(sign, 0, 10.7, 0.45); g.add(sign); g.add(at(rbox(11.6, 2.3, 0.3, '#2a2a2a', 0.06), 0, 10.7, 0.25));
  // vitrine
  for (const [x, y, ww, hh] of [[-2, 7.1, 10.4, 0.4], [-2, 1.1, 10.4, 0.4], [-7.0, 4.1, 0.4, 6.2], [3.0, 4.1, 0.4, 6.2]]) g.add(at(rbox(ww, hh, 0.5, '#d8c49a', 0.08), x, y, 0.05));
  const inside = at(rbox(10.2, 6.2, 0.2, '#f3e6c8', 0.04, { emissive: '#ffe2a8', emissiveIntensity: 0.35 }), -2, 4.1, -2.0); g.add(inside);
  g.add(at(rbox(9.6, 0.5, 1.8, '#5a2a30', 0.05), -2, 1.35, -0.8));
  const glass = new THREE.Mesh(new THREE.PlaneGeometry(9.6, 5.6), new THREE.MeshStandardMaterial({ color: '#cfe8f7', transparent: true, opacity: 0.14, roughness: 0.05, metalness: 0.2 }));
  at(glass, -2, 4.1, 0.3); g.add(glass);
  // mannequin + manteau rouge
  const man = new THREE.Group(); at(man, -2, 1.6, -0.9); g.add(man);
  man.add(at(rbox(0.25, 1.2, 0.25, '#5a4a3a', 0.04), 0, 0.6, 0));
  man.add(at(rbox(2.0, 3.0, 1.1, '#c62828', 0.18), 0, 2.6, 0));
  man.add(at(rbox(2.1, 0.45, 1.2, '#f2ece0', 0.18), 0, 4.0, 0));
  for (const s of [-1, 1]) man.add(at(rbox(0.8, 2.3, 0.8, '#c62828', 0.14), s * 1.35, 2.9, 0));
  for (let i = 0; i < 3; i++) man.add(at(rbox(0.16, 0.16, 0.06, '#2b2b2b', 0.05), 0, 3.5 - i * 0.6, 0.58));
  man.add(at(rbox(0.9, 0.9, 0.9, '#e9dcc6', 0.4), 0, 4.75, 0));
  // etiquettes : vieille etiquette (40, jaunie) derriere l'etiquette promo, qui depasse en bas a gauche
  const tagG = new THREE.Group(); at(tagG, 1.0, 2.35, -0.25); g.add(tagG);
  const oldTag = plane(0.62, 0.78, tagTex('old')); at(oldTag, -0.2, -0.3, 0.0); oldTag.rotation.z = 0.12; tagG.add(oldTag);
  const promoPivot = new THREE.Group(); at(promoPivot, 0, 0.45, 0.03); tagG.add(promoPivot);
  const promo = plane(0.8, 1.0, tagTex('promo')); at(promo, 0, -0.5, 0); promoPivot.add(promo);
  tagG.add(at(rbox(0.04, 0.8, 0.04, '#999', 0.01), 0, 0.85, 0.0));
  // porte d'entree + caisse du marchand
  g.add(at(rbox(2.6, 5.2, 0.3, '#3b1f24', 0.06), 5.4, 2.6, 0.1));
  g.add(at(rbox(0.25, 0.25, 0.2, PAL.gold, 0.05), 4.6, 2.6, 0.35));
  const crate = at(rbox(1.8, 1.0, 1.4, PAL.wood, 0.06), 5.8, 0.5, 2.4); g.add(crate);
  // banderole -60 %
  const ban = plane(6.5, 1.3, canvasTex(1024, 200, (c, w, h) => { c.fillStyle = '#d42b1e'; c.fillRect(0, 0, w, h); c.fillStyle = '#fff'; c.font = '900 130px Montserrat, Arial Black, sans-serif'; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText('-60 %', w / 2, h / 2 + 8); }), { double: true });
  at(ban, -2, 7.75, 0.42); g.add(ban);
  g.userData = { tagG, promoPivot, oldTag, man, crate: [5.8, 1.0, 2.4], inside };
  return shadow(g);
}

export function makePiggyBank() {
  const g = new THREE.Group(); g.name = 'piggy';
  const pink = '#f5a3b8';
  g.add(at(rbox(1.3, 1.0, 0.95, pink, 0.4), 0, 0.6, 0));
  g.add(at(rbox(0.45, 0.4, 0.4, '#f28aa3', 0.15), 0, 0.62, 0.62));
  for (const s of [-1, 1]) { g.add(at(rbox(0.25, 0.3, 0.12, pink, 0.06), s * 0.32, 1.18, 0.25)); for (const z of [-0.3, 0.3]) g.add(at(rbox(0.22, 0.3, 0.22, '#f28aa3', 0.06), s * 0.4, 0.12, z)); }
  g.add(at(rbox(0.5, 0.06, 0.12, '#3b1f24', 0.02), 0, 1.12, 0));
  for (const s of [-1, 1]) g.add(at(rbox(0.1, 0.12, 0.05, '#1b1b1b', 0.03), s * 0.22, 0.9, 0.48));
  return shadow(g);
}

export function makeNotebook(o = {}) {
  const tex = canvasTex(512, 384, () => {});
  const draw = (hl = 0) => {
    const g = tex.userData.ctx, w = 512, h = 384;
    if (o.rows) {   // ep06 : carnet de Noe (dates, montants)
      g.fillStyle = '#f7f1e1'; g.fillRect(0, 0, w, h);
      g.strokeStyle = 'rgba(60,90,160,0.25)'; g.lineWidth = 2; for (let y = 70; y < h; y += 44) { g.beginPath(); g.moveTo(20, y); g.lineTo(w - 20, y); g.stroke(); }
      g.fillStyle = '#23305a'; g.font = '700 34px Montserrat, Arial, sans-serif'; g.textAlign = 'left'; g.fillText(o.title || '', 30, 50);
      o.rows.forEach(([a, b], i) => { const y = 108 + i * 44; g.fillStyle = '#23305a'; g.font = '700 32px Montserrat, Arial, sans-serif'; g.textAlign = 'left'; g.fillText(a, 32, y); g.textAlign = 'right'; g.fillStyle = '#b3261e'; g.fillText(b, w - 30, y); });
      tex.needsUpdate = true; return;
    }
    g.fillStyle = '#f7f1e1'; g.fillRect(0, 0, w, h);
    g.strokeStyle = 'rgba(60,90,160,0.25)'; g.lineWidth = 2; for (let y = 70; y < h; y += 44) { g.beginPath(); g.moveTo(20, y); g.lineTo(w - 20, y); g.stroke(); }
    g.fillStyle = '#7a1f1f'; g.fillRect(w / 2 - 3, 0, 6, h);
    g.fillStyle = '#23305a'; g.font = '700 30px Montserrat, Arial, sans-serif'; g.textAlign = 'left';
    g.fillText('Il y a 1 mois', 30, 50);
    const rows = [['Manteau', '40'], ['Bonnet', '6'], ['Gants', '5'], ['Lanterne', '9']];
    rows.forEach(([a, b], i) => { const y = 108 + i * 44; if (i === 0 && hl > 0) { g.fillStyle = `rgba(255,230,0,${0.75 * hl})`; g.fillRect(24, y - 34, 220, 42); }
      g.fillStyle = '#23305a'; g.font = '700 32px Montserrat, Arial, sans-serif'; g.fillText(a, 32, y); g.textAlign = 'right'; g.fillText(b, 236, y); g.textAlign = 'left'; });
    g.fillStyle = '#23305a'; g.font = '700 30px Montserrat, Arial, sans-serif'; g.fillText('Vendredi', 285, 50);
    rows.forEach(([a], i) => { const y = 108 + i * 44; g.fillText(a.slice(0, 6) + '.', 290, y); g.textAlign = 'right'; g.fillStyle = '#c0392b'; g.fillText(['40', '6', '5', '9'][i], w - 28, y); g.textAlign = 'left'; g.fillStyle = '#23305a'; });
    tex.needsUpdate = true;
  };
  draw(0);
  const g = new THREE.Group(); g.name = 'notebook';
  g.add(at(rbox(1.75, 0.08, 1.3, '#7a1f1f', 0.03), 0, -0.05, 0));
  const pg = plane(1.66, 1.24, tex); pg.rotation.x = -Math.PI / 2; at(pg, 0, 0.0, 0); g.add(pg);
  g.userData = { draw, page: pg };
  return shadow(g);
}

export function makeDishes() {
  const g = new THREE.Group(); g.name = 'dishes';
  g.add(at(rbox(4.4, 2.2, 2.0, '#8a7a66', 0.08), 0, 1.1, 0));
  g.add(at(rbox(2.6, 0.3, 1.5, '#6a7d8a', 0.06, { metalness: 0.4 }), -0.4, 2.25, 0));
  const water = new THREE.Mesh(new THREE.PlaneGeometry(2.3, 1.2), mat('#a7c7d6', { roughness: 0.1, metalness: 0.2 })); water.rotation.x = -Math.PI / 2; at(water, -0.4, 2.41, 0); g.add(water);
  const plates = new THREE.Group(); at(plates, 1.55, 2.2, 0); g.add(plates);
  const pg = new THREE.CylinderGeometry(0.42, 0.36, 0.06, 20), pm = mat('#f7f7f2', { roughness: 0.4 });
  for (let i = 0; i < 16; i++) { const m = new THREE.Mesh(pg, pm); at(m, Math.sin(i * 1.3) * 0.03, 0.04 + i * 0.075, Math.cos(i) * 0.03); m.castShadow = true; plates.add(m); }
  const plate = new THREE.Mesh(pg, pm); plate.rotation.x = 1.2; at(plate, -0.4, 2.7, 0.2); g.add(plate);
  g.userData = { plates, plate };
  return shadow(g);
}

export function makeBonnet() {
  const g = new THREE.Group(); g.name = 'bonnet';
  const halves = [];
  for (const s of [-1, 1]) { const h = new THREE.Group(); at(h, s * 0.02, 0, 0); g.add(h);
    h.add(at(rbox(0.6, 0.7, 1.2, '#3f6fb5', 0.25), s * 0.3, 0.35, 0)); h.add(at(rbox(0.62, 0.22, 1.25, '#f2ece0', 0.08), s * 0.3, 0.08, 0)); halves.push(h); }
  const pom = at(new THREE.Mesh(new THREE.SphereGeometry(0.22, 12, 10), mat('#f2ece0')), 0, 0.82, 0); g.add(pom);
  const thread = at(rbox(0.03, 0.03, 0.9, '#f2ece0', 0.01), 0, 0.5, 0); g.add(thread);
  g.userData = { halves, pom, thread };
  return shadow(g);
}

export function makeBag(color = '#e8d5b0') {
  const g = new THREE.Group();
  g.add(at(rbox(0.9, 1.0, 0.45, color, 0.06), 0, -0.5, 0));
  g.add(at(rbox(0.5, 0.08, 0.08, '#5a3a2a', 0.02), 0, 0.1, 0));
  return shadow(g);
}

// ---------------- ep06 : decors et accessoires ----------------
// Affiche « PRIME 50 % » (torn = dechiree pour la fin)
export function makePoster(o = {}) {
  const tex = canvasTex(600, 800, () => {});
  const draw = (torn = false) => {
    const g = tex.userData.ctx, w = 600, h = 800;
    g.clearRect(0, 0, w, h);
    g.fillStyle = '#f3ead2'; g.fillRect(0, 0, w, h);
    g.fillStyle = '#b3261e'; g.fillRect(0, 0, w, 150);
    g.fillStyle = '#ffffff'; g.font = '900 92px Montserrat, Arial Black, sans-serif'; g.textAlign = 'center'; g.fillText('PRIME', w / 2, 112);
    g.fillStyle = '#b3261e'; g.font = '900 230px Montserrat, Arial Black, sans-serif'; g.fillText('50%', w / 2, 400);
    g.fillStyle = '#23262e'; g.font = '800 46px Montserrat, Arial, sans-serif';
    ['À QUI DÉNONCE', 'UN FRAUDEUR'].forEach((s, i) => g.fillText(s, w / 2, 500 + i * 62));
    g.font = '700 30px Montserrat, Arial, sans-serif'; g.fillStyle = '#5a5d66'; g.fillText('Avis officiel de la ville', w / 2, 690);
    if (torn) { g.globalCompositeOperation = 'destination-out'; g.beginPath(); g.moveTo(w, 260); g.lineTo(380, 420); g.lineTo(450, 520); g.lineTo(330, 640); g.lineTo(420, h); g.lineTo(w, h); g.closePath(); g.fill(); g.globalCompositeOperation = 'source-over'; }
    tex.needsUpdate = true;
  };
  draw(!!o.torn);
  const g = new THREE.Group(); g.name = 'poster';
  const p = plane(1.8, 2.4, tex, { transparent: true }); g.add(p);
  g.userData = { draw };
  return g;
}

// Telephone dans la main : ecran texte (draw(lignes, couleur))
export function makePhone() {
  const tex = canvasTex(360, 640, () => {});
  const draw = (lines = ['₿'], color = '#f7931a', bg = '#10131c') => {
    const g = tex.userData.ctx, w = 360, h = 640;
    g.fillStyle = bg; g.fillRect(0, 0, w, h);
    g.textAlign = 'center'; g.textBaseline = 'middle';
    lines.forEach((s, i) => { const big = i === 0; g.fillStyle = big ? color : '#e9edf5'; g.font = (big ? '900 ' + (s.length > 6 ? 64 : 150) : '800 40') + 'px Montserrat, Arial, sans-serif'; g.fillText(s, w / 2, h / 2 - (lines.length - 1) * 50 + i * 100); });
    tex.needsUpdate = true;
  };
  draw();
  const g = new THREE.Group(); g.name = 'phone';
  g.add(rbox(0.62, 1.12, 0.08, '#1b1d22', 0.06));
  const s = plane(0.54, 0.96, tex); s.position.z = 0.045; g.add(s);
  const glow = new THREE.PointLight('#9fc3ff', 0, 3); glow.position.set(0, 0, 0.6); g.add(glow);
  g.userData = { draw, glow, screen: s };
  return g;
}

export function makeSuitcase() {
  const g = new THREE.Group(); g.name = 'suitcase';
  g.add(at(rbox(2.2, 0.5, 1.5, '#6e3b3b', 0.08), 0, 0.25, 0));
  const lid = new THREE.Group(); at(lid, 0, 0.5, -0.75); g.add(lid);
  const l = at(rbox(2.2, 0.4, 1.5, '#7d4545', 0.08), 0, 0.2, 0.75); lid.add(l); lid.rotation.x = -1.9;
  [['#d98fa6', -0.5, 0.2], ['#f2ece0', 0.4, -0.3], ['#5b4a6e', 1.4, 0.9], ['#d98fa6', -1.5, 1.0]].forEach(([c, x, z]) => g.add(at(rbox(0.9, 0.08, 0.7, c, 0.03), x, 0.55 + (x > 1 || x < -1 ? -0.5 : 0), z)));
  return shadow(g);
}

// Cage d'escalier : marches, palier, porte de l'appartement de la mere de Noe, applique murale
export function makeStairwell() {
  const g = new THREE.Group(); g.name = 'stairwell';
  g.add(at(rbox(60, 0.3, 60, '#5f5c58', 0.04), 6, -0.11, 12));                 // sol beton (large : on ne voit pas l'herbe)
  g.add(at(rbox(0.4, 12, 40, '#7d776b', 0.05), 22, 6, 6)); g.add(at(rbox(44, 12, 0.4, '#7d776b', 0.05), 0, 6, 34));   // murs lointains
  g.add(at(rbox(14, 12, 0.4, '#8f8a7d', 0.05), 0, 6, -7));                   // mur du fond
  g.add(at(rbox(0.4, 12, 14, '#857f72', 0.05), -7, 6, 0));                   // mur gauche
  g.add(at(rbox(14, 0.5, 0.06, '#5d594f', 0.02), 0, 3.0, -6.77));            // plinthe sale
  for (let i = 0; i < 7; i++) g.add(at(rbox(6, 0.5, 1.1, '#9c968a', 0.04), 3.5, 0.25 + i * 0.5, 2.5 - i * 1.1));   // marches qui montent vers le fond
  g.add(at(rbox(6, 0.12, 0.12, '#3b3b3b', 0.03), 3.5, 4.2, -0.8)); for (let i = 0; i < 5; i++) g.add(at(rbox(0.08, 1.2, 0.08, '#3b3b3b', 0.02), 0.6, 0.9 + i * 0.5, 2.3 - i * 1.4));
  const door = new THREE.Group(); door.name = 'apartDoor'; at(door, -3.6, 0, -6.75); g.add(door);   // charniere a gauche
  door.add(at(rbox(2.6, 5.4, 0.22, '#4a3a2e', 0.05), 1.3, 2.7, 0));
  door.add(at(rbox(0.18, 0.18, 0.2, '#c9a64a', 0.05, { metalness: 0.7, roughness: 0.3 }), 2.25, 2.6, 0.18));
  g.add(at(rbox(3.2, 5.8, 0.15, '#3a2e25', 0.04), -2.3, 2.9, -6.85));
  const lampMat = new THREE.MeshStandardMaterial({ color: '#fff2c4', emissive: '#ffd27a', emissiveIntensity: 1.6 });
  const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.35, 16, 10), lampMat); at(lamp, 0.4, 7.4, -6.6); g.add(lamp);
  const light = new THREE.PointLight('#ffd9a0', 9, 18, 1.6); at(light, 0.4, 7.0, -5.8); g.add(light);
  g.userData = { door, lamp, lampMat, light, setLamp(on) { lampMat.emissiveIntensity = on ? 1.6 : 0.05; light.intensity = on ? 9 : 0; } };
  return shadow(g);
}

// Ruelle : mur de briques avec l'affiche, banc, lampadaire
export function makeAlley() {
  const g = new THREE.Group(); g.name = 'alley';
  g.add(at(rbox(30, 0.3, 20, '#4b4f57', 0.04), 0, -0.15, 0));
  const bt = canvasTex(256, 256, (x, w, h) => { x.fillStyle = '#7d3b2c'; x.fillRect(0, 0, w, h); x.fillStyle = '#5a2a20'; for (let r = 0; r < 8; r++) { x.fillRect(0, r * 32, w, 3); for (let c = 0; c < 4; c++) x.fillRect(((r % 2) * 32 + c * 64) % w, r * 32, 3, 32); } });
  bt.wrapS = bt.wrapT = THREE.RepeatWrapping; bt.repeat.set(6, 3);
  const wall = new THREE.Mesh(new THREE.BoxGeometry(30, 12, 0.6), new THREE.MeshStandardMaterial({ map: bt, roughness: 0.95 })); at(wall, 0, 6, -5); wall.receiveShadow = true; g.add(wall);
  const poster = makePoster(); at(poster, 0, 4.6, -4.68); g.add(poster);
  const bench = new THREE.Group(); at(bench, 6, 0, -3.4); g.add(bench);
  bench.add(at(rbox(4, 0.25, 1.2, '#7a5236', 0.05), 0, 1.4, 0)); bench.add(at(rbox(4, 1.0, 0.2, '#7a5236', 0.05), 0, 2.2, -0.55));
  for (const s of [-1, 1]) bench.add(at(rbox(0.2, 1.4, 1.0, '#2b2b2b', 0.03), s * 1.7, 0.7, 0));
  g.add(at(rbox(0.25, 8, 0.25, '#2b2f36', 0.05), -8, 4, -3.5));
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.45, 16, 10), new THREE.MeshStandardMaterial({ color: '#fff0c0', emissive: '#ffcf7a', emissiveIntensity: 1.8 })); at(head, -8, 8.2, -3.5); g.add(head);
  const light = new THREE.PointLight('#ffd49a', 10, 22, 1.5); at(light, -7.6, 7.6, -2.5); g.add(light);
  g.userData = { poster, bench, light };
  return shadow(g);
}

// Interieur de Petit Shark : table de cuisine, etagere avec dossier « DECLARE ✓ »
export function makeSharkHome() {
  const g = new THREE.Group(); g.name = 'sharkHome';
  const ft = canvasTex(256, 256, (x, w, h) => { for (let i = 0; i < 8; i++) for (let j = 0; j < 8; j++) { x.fillStyle = (i + j) % 2 ? '#e8e2d6' : '#c9c0ae'; x.fillRect(i * 32, j * 32, 32, 32); } });
  ft.wrapS = ft.wrapT = THREE.RepeatWrapping; ft.repeat.set(4, 4);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(18, 18), new THREE.MeshStandardMaterial({ map: ft, roughness: 0.85 })); floor.rotation.x = -Math.PI / 2; floor.position.y = 0.02; floor.receiveShadow = true; g.add(floor);
  g.add(at(rbox(18, 9, 0.4, '#b9d3d8', 0.05), 0, 4.5, -9)); g.add(at(rbox(0.4, 9, 18, '#a9c4ca', 0.05), -9, 4.5, 0));
  const win = new THREE.Group(); at(win, 3.5, 5, -8.75); g.add(win);
  win.add(rbox(3.4, 2.8, 0.2, '#f2ead8', 0.04));
  const glass = at(rbox(3.0, 2.4, 0.1, '#1a2a55', 0.02, { emissive: '#22356e', emissiveIntensity: 0.6 }), 0, 0, 0.08); win.add(glass);
  const table = new THREE.Group(); at(table, 0, 0, -2); g.add(table);
  table.add(at(rbox(5, 0.25, 3, '#c9955e', 0.06), 0, 2.4, 0));
  for (const [x, z] of [[-2.2, -1.2], [2.2, -1.2], [-2.2, 1.2], [2.2, 1.2]]) table.add(at(rbox(0.25, 2.3, 0.25, '#8a6440', 0.04), x, 1.15, z));
  const paper = at(rbox(0.9, 0.02, 1.2, '#fbfaf5', 0.01), 0.4, 2.54, 0.4); paper.rotation.y = 0.3; table.add(paper);
  const shelf = new THREE.Group(); at(shelf, -5.5, 0, -8.5); g.add(shelf);
  shelf.add(at(rbox(4.5, 0.2, 1.0, '#7a5236', 0.04), 0, 5.2, 0)); shelf.add(at(rbox(4.5, 0.2, 1.0, '#7a5236', 0.04), 0, 3.4, 0));
  const ftex = canvasTex(256, 360, (x, w, h) => { x.fillStyle = '#2e7d4f'; x.fillRect(0, 0, w, h); x.fillStyle = '#ffffff'; x.font = '900 40px Montserrat, Arial, sans-serif'; x.textAlign = 'center'; x.fillText('DÉCLARÉ', w / 2, 150); x.font = '900 120px Montserrat, Arial, sans-serif'; x.fillText('✓', w / 2, 290); });
  const folder = new THREE.Group(); at(folder, 0.6, 5.3, 0.3); shelf.add(folder);
  folder.add(at(rbox(1.1, 1.5, 0.3, '#2e7d4f', 0.04), 0, 0.75, 0));
  const lab = plane(1.0, 1.4, ftex); at(lab, 0, 0.75, 0.16); folder.add(lab);
  [['#c0392b', -1.4], ['#2c3e70', -0.9], ['#d4a017', 1.6]].forEach(([c, x]) => shelf.add(at(rbox(0.4, 1.4, 0.9, c, 0.03), x, 6.0, 0)));
  const lampMat = new THREE.MeshStandardMaterial({ color: '#fff6d8', emissive: '#ffd27a', emissiveIntensity: 1.4 });
  const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.4, 16, 10), lampMat); at(bulb, 0, 8.0, -2); g.add(bulb);
  const light = new THREE.PointLight('#ffe0b0', 12, 26, 1.4); at(light, 0, 7.2, -1.5); g.add(light);
  g.userData = { table, paper, shelf, folder, glass, light, lampMat };
  return shadow(g);
}

// --- ep05 : compteur de vie au poignet (« on paie avec sa vie »), gros plan de poignet, jetons-parts, boulangerie
function drawClockFace(g, w, h, big, small, color, glow) {
  g.clearRect(0, 0, w, h);
  g.fillStyle = '#0c0f14'; g.beginPath(); g.roundRect(4, 4, w - 8, h - 8, h * 0.18); g.fill();
  g.strokeStyle = color; g.lineWidth = Math.max(4, h * 0.05); g.globalAlpha = 0.85; g.beginPath(); g.roundRect(10, 10, w - 20, h - 20, h * 0.14); g.stroke(); g.globalAlpha = 1;
  g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillStyle = color;
  g.shadowColor = color; g.shadowBlur = 18 * glow;
  const fit = (txt, wt, px) => { g.font = `${wt} ${px}px Montserrat, Arial Black, sans-serif`; const m = g.measureText(txt).width; if (m > w * 0.8) { px = Math.floor(px * w * 0.8 / m); g.font = `${wt} ${px}px Montserrat, Arial Black, sans-serif`; } };
  fit(big, 900, Math.round(h * (small ? 0.4 : 0.52))); g.fillText(big, w / 2, h * (small ? 0.4 : 0.52));
  if (small) { fit(small, 700, Math.round(h * 0.2)); g.fillText(small, w / 2, h * 0.74); }
  g.shadowBlur = 0;
}
export function makeWristClock() {
  const tex = canvasTex(512, 300, (g, w, h) => drawClockFace(g, w, h, '10 ANS', '00 J 00:00:00', '#38e8ff', 1));
  const m = plane(1.0, 0.59, tex, { emissive: 1.4 }); m.castShadow = false; m.material.toneMapped = false;
  m.userData.draw = (big, small, color = '#38e8ff', glow = 1) => {
    const key = big + '|' + small + '|' + color; if (m.userData.last === key) return; m.userData.last = key;
    drawClockFace(tex.userData.ctx, 512, 300, big, small, color, glow); tex.needsUpdate = true;
  };
  return m;
}
// Gros plan : avant-bras couche (manche + main), cadran sur le dessus, oriente vers +z / le haut
export function makeBigWrist(o = {}) {
  const c = { skin: '#f0c9a0', sleeve: '#3f8fd2', ...o };
  const g = new THREE.Group(); g.name = 'bigWrist';
  g.add(at(rbox(2.3, 2.3, 7.0, c.sleeve, 0.3), 0, 0, -4.2));
  g.add(at(rbox(2.4, 2.4, 0.5, c.cuff || c.sleeve, 0.15), 0, 0, -0.85));
  g.add(at(rbox(2.1, 2.0, 2.6, c.skin, 0.4), 0, 0, 0.6));
  g.add(at(rbox(1.9, 1.7, 1.8, c.skin, 0.5), 0, -0.1, 2.6));
  const face = makeWristClock(); face.scale.setScalar(1.95); face.rotation.x = -Math.PI / 2; at(face, 0, 1.03, 0.6); g.add(face);
  g.userData = { face, draw: face.userData.draw };
  return shadow(g);
}
export function makeToken() {
  const g = new THREE.Group();
  const ring = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 0.07, 20), new THREE.MeshStandardMaterial({ color: PAL.gold, metalness: 0.8, roughness: 0.3, emissive: '#b8860b', emissiveIntensity: 0.5 }));
  ring.rotation.x = Math.PI / 2; g.add(ring);
  const loaf = rbox(0.38, 0.2, 0.06, '#c8813a', 0.08); at(loaf, 0, 0, 0.05); g.add(loaf);
  for (const x of [-0.09, 0.05]) g.add(at(rbox(0.04, 0.16, 0.02, '#f3d29a', 0.01), x, 0, 0.085));
  return g;
}
// 15 jetons sur la poitrine (torse local), userData.setCount(n), userData.glow(v)
export function makeTokenBadges() {
  const g = new THREE.Group(); const list = [];
  for (let i = 0; i < 15; i++) { const t = makeToken(); at(t, -0.72 + (i % 5) * 0.36, 1.78 - Math.floor(i / 5) * 0.4, 0.53); t.scale.setScalar(0.9); g.add(t); list.push(t); }
  g.userData = { list, setCount: (n) => list.forEach((t, i) => (t.visible = i < n)), glow: (v) => list.forEach((t) => (t.children[0].material.emissiveIntensity = v)) };
  list.forEach((t) => { t.children[0].material = t.children[0].material.clone(); });
  return g;
}
export function makeBakery() {
  const g = new THREE.Group(); g.name = 'bakery';
  g.add(at(rbox(6.4, 1.6, 2.0, PAL.woodDark, 0.06), 0, 0.8, 0));
  g.add(at(rbox(6.6, 0.22, 2.2, PAL.wood, 0.05), 0, 1.7, 0));
  for (const x of [-3.0, 3.0]) for (const z of [-0.9, 0.9]) g.add(at(rbox(0.18, 4.4, 0.18, PAL.woodDark, 0.03), x, 2.2, z));
  const tex = canvasTex(256, 64, (cx) => { for (let i = 0; i < 8; i++) { cx.fillStyle = i % 2 ? '#fbf6ec' : '#e08a1e'; cx.fillRect(i * 32, 0, 32, 64); } });
  const awn = new THREE.Mesh(new THREE.BoxGeometry(7.2, 0.14, 2.8), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.8 })); awn.rotation.x = 0.2; at(awn, 0, 4.45, 0.2); awn.castShadow = true; g.add(awn);
  for (let i = 0; i < 7; i++) { const l = rbox(0.75, 0.38, 0.42, i % 2 ? '#c8813a' : '#b56a2a', 0.18); at(l, -2.6 + i * 0.86, 2.02, 0.1 + (i % 2) * 0.35); l.rotation.y = 0.2 * (i % 3 - 1); g.add(l); }
  for (let i = 0; i < 4; i++) { const b = rbox(1.6, 0.22, 0.26, '#d9a24e', 0.1); at(b, -2.2 + i * 1.5, 2.05, -0.55); b.rotation.y = 0.15; g.add(b); }
  const sign = plane(5.2, 1.1, textTex('BOULANGERIE', { w: 1024, h: 220, bg: '#f6ead2', fg: '#7a3e12', border: '#7a3e12', font: '900 150px Montserrat, Arial Black, sans-serif' }), { double: true }); at(sign, 0, 5.35, 1.45); sign.rotation.x = -0.1; g.add(sign);
  return shadow(g);
}
