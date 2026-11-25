// Docteur Shark : personnage principal, version "blocky" facon Roblox (R6).
// Repere : y vers le haut, le personnage regarde vers +z. 1 unite ~ 1 stud.
import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

export const SHARK_COLORS = {
  skinDark: '#577d94',   // dessus de la tete, ailerons
  skinMid: '#6a8ca3',    // mains
  skinLight: '#92acb9',  // machoire / ventre
  gill: '#3f5a6b',
  cap: '#4091e3', capDark: '#2f74c4',
  badge: '#dde0e5', badgeInner: '#a9aeb2',
  frame: '#328bef', lens: '#3c2374', lensHi: '#b274f0',
  hoodie: '#f5f8fb', hoodieShade: '#e2e8ee', string: '#141414',
  jeans: '#2e3a4f', shoe: '#f4f6f8', sole: '#c3ccd6',
  mouth: '#0b0b0f', teeth: '#fdfdfd',
};

const matCache = new Map();
export function mat(color, opts = {}) {
  const key = color + JSON.stringify(opts);
  if (!matCache.has(key)) {
    const physical = opts.physical;
    const o = { ...opts }; delete o.physical;
    matCache.set(key, physical
      ? new THREE.MeshPhysicalMaterial({ color, roughness: 0.1, metalness: 0.05, clearcoat: 1, clearcoatRoughness: 0.05, ...o })
      : new THREE.MeshStandardMaterial({ color, roughness: 0.62, metalness: 0, ...o }));
  }
  return matCache.get(key);
}

export function rbox(w, h, d, color, r = 0.12, opts = {}) {
  const rad = Math.max(0.005, Math.min(r, w / 2 - 0.002, h / 2 - 0.002, d / 2 - 0.002));
  const m = new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 3, rad), typeof color === 'string' ? mat(color, opts) : color);
  m.castShadow = true; m.receiveShadow = true;
  return m;
}

export function finMesh(points, thickness, color) {
  const s = new THREE.Shape();
  points.forEach(([x, y], i) => (i ? s.lineTo(x, y) : s.moveTo(x, y)));
  s.closePath();
  const bev = Math.min(0.06, thickness / 3);
  const g = new THREE.ExtrudeGeometry(s, { depth: thickness - 2 * bev, bevelEnabled: true, bevelThickness: bev, bevelSize: bev, bevelSegments: 3, curveSegments: 8 });
  g.translate(0, 0, -(thickness - 2 * bev) / 2);
  const m = new THREE.Mesh(g, mat(color));
  m.castShadow = true; m.receiveShadow = true;
  return m;
}

function at(obj, x, y, z) { obj.position.set(x, y, z); return obj; }

export function makeDocShark(opts = {}) {
  const C = { ...SHARK_COLORS, ...(opts.colors || {}) };
  const root = new THREE.Group(); root.name = 'DocShark';

  const legs = {};
  for (const [name, s] of [['legL', -1], ['legR', 1]]) {
    const p = new THREE.Group(); p.name = name; at(p, s * 0.5, 2.0, 0);
    p.add(at(rbox(0.96, 1.7, 0.96, C.jeans, 0.12), 0, -0.85, 0));
    p.add(at(rbox(1.0, 0.36, 1.16, C.shoe, 0.12), 0, -1.82, 0.07));
    p.add(at(rbox(1.02, 0.09, 1.18, C.sole, 0.04), 0, -1.955, 0.07));
    root.add(p); legs[name] = p;
  }

  const torso = new THREE.Group(); torso.name = 'torso'; at(torso, 0, 2.0, 0); root.add(torso);
  torso.add(at(rbox(2.0, 1.98, 1.0, C.hoodie, 0.14), 0, 1.0, 0));
  torso.add(at(rbox(2.03, 0.2, 1.03, C.hoodieShade, 0.07), 0, 0.1, 0));          // bas cotele
  torso.add(at(rbox(1.2, 0.55, 0.06, C.hoodieShade, 0.06), 0, 0.62, 0.5));       // poche kangourou
  torso.add(at(rbox(1.42, 0.24, 1.0, C.hoodie, 0.1), 0, 2.0, -0.02));            // col de capuche
  torso.add(at(rbox(1.45, 0.82, 0.36, C.hoodie, 0.16), 0, 1.72, -0.64));         // capuche dans le dos
  for (const s of [-1, 1]) {                                                       // cordons
    torso.add(at(rbox(0.07, 0.64, 0.07, C.string, 0.03), s * 0.27, 1.62, 0.535));
    torso.add(at(rbox(0.11, 0.14, 0.11, '#2b2b2b', 0.04), s * 0.27, 1.25, 0.535));
  }
  const tail = finMesh([[0, -0.12], [0.55, -0.05], [1.0, 0.75], [0.62, 0.08], [0.95, -0.55], [0.5, -0.22], [0, -0.3]], 0.18, C.skinDark);
  tail.rotation.y = Math.PI / 2; at(tail, 0, 0.42, -0.45); torso.add(tail);

  const arms = {};
  for (const [name, s] of [['armL', -1], ['armR', 1]]) {
    const p = new THREE.Group(); p.name = name; at(p, s * 1.48, 3.95, 0);
    p.add(at(rbox(0.94, 1.52, 0.94, C.hoodie, 0.13), 0, -0.76, 0));
    p.add(at(rbox(0.97, 0.18, 0.97, C.hoodieShade, 0.06), 0, -1.56, 0));
    p.add(at(rbox(0.86, 0.44, 0.86, C.skinMid, 0.15), 0, -1.84, 0));
    root.add(p); arms[name] = p;
  }

  const head = new THREE.Group(); head.name = 'head'; at(head, 0, 4.0, 0.05); root.add(head);
  head.scale.setScalar(opts.headScale || 1.12);   // tete un peu plus grosse : lisible sur mobile
  const HZ = 0.1;              // decalage avant de la tete
  const FRONT = HZ + 0.995;    // face avant du museau (le haut deborde sur la machoire)
  head.add(at(rbox(1.9, 1.02, 1.85, C.skinDark, 0.24), 0, 1.05, HZ + 0.07));  // haut de tete + museau
  head.add(at(rbox(1.8, 0.6, 1.6, C.skinLight, 0.22), 0, 0.31, HZ - 0.05));   // machoire claire, en retrait
  head.add(at(rbox(1.36, 0.1, 0.06, C.mouth, 0.03), 0, 0.64, FRONT + 0.005));
  for (const x of [-0.42, 0.0, 0.42]) head.add(at(rbox(0.18, 0.2, 0.08, C.teeth, 0.03), x, 0.5, FRONT - 0.02));
  for (const s of [-1, 1]) for (const z of [-0.3, -0.08, 0.14]) {
    head.add(at(rbox(0.04, 0.34, 0.07, C.gill, 0.015), s * 0.91, 0.38, HZ + z - 0.05));
  }
  for (const s of [-1, 1]) {
    const f = finMesh([[0, 0.32], [0.82, 0.46], [0.6, 0.22], [0, -0.34]], 0.22, C.skinDark);
    f.scale.x = s; f.rotation.y = s * 0.35; at(f, s * 0.9, 1.0, HZ - 0.1); head.add(f);
  }
  const dorsal = finMesh([[-0.5, 0], [0.42, 0], [0.2, 0.35], [-0.42, 0.98], [-0.48, 0.5]], 0.24, C.skinDark);
  dorsal.rotation.y = -Math.PI / 2; at(dorsal, 0, 1.6, HZ - 0.55); head.add(dorsal);

  const lenses = [];   // ep06 : verres (clin d'oeil = verre droit aplati)
  const lensMat = mat(C.lens, { physical: true, emissive: '#1a0d3a', emissiveIntensity: 0.4 });
  if (opts.glasses === false) {                                                      // yeux visibles (sans lunettes)
    for (const s of [-1, 1]) {
      head.add(at(rbox(0.46, 0.42, 0.06, '#fbfbfb', 0.1), s * 0.45, 1.12, FRONT + 0.02));
      head.add(at(rbox(0.24, 0.28, 0.05, '#141418', 0.08), s * 0.42, 1.1, FRONT + 0.05));
      head.add(at(rbox(0.08, 0.08, 0.02, '#ffffff', 0.02), s * 0.42 + 0.05, 1.18, FRONT + 0.075));
      if (opts.lashes) for (const k of [-1, 0, 1]) {
        const l = at(rbox(0.04, 0.14, 0.03, '#141418', 0.01), s * 0.45 + k * 0.13, 1.38, FRONT + 0.04); l.rotation.z = -k * 0.35; head.add(l);
      }
    }
  } else for (const s of [-1, 1]) {
    head.add(at(rbox(0.82, 0.5, 0.08, C.frame, 0.08), s * 0.45, 1.12, FRONT + 0.02));
    const lens = at(rbox(0.68, 0.36, 0.05, lensMat, 0.06), s * 0.45, 1.12, FRONT + 0.055); head.add(lens); lenses.push(lens);
    const hi1 = at(rbox(0.07, 0.3, 0.02, C.lensHi, 0.01, { emissive: C.lensHi, emissiveIntensity: 0.35 }), s * 0.45 - 0.1, 1.13, FRONT + 0.083);
    hi1.rotation.z = -0.55; head.add(hi1); lenses.push(hi1);
    const hi2 = at(rbox(0.04, 0.2, 0.02, C.lensHi, 0.01, { emissive: C.lensHi, emissiveIntensity: 0.35 }), s * 0.45 + 0.03, 1.13, FRONT + 0.083);
    hi2.rotation.z = -0.55; head.add(hi2); lenses.push(hi2);
    head.add(at(rbox(0.06, 0.07, 1.05, C.frame, 0.03), s * 0.975, 1.2, HZ + 0.4));   // branches
  }
  if (opts.glasses !== false) head.add(at(rbox(0.2, 0.08, 0.07, C.frame, 0.03), 0, 1.2, FRONT + 0.02));          // pont

  const CAP = { x: 1.02, y: 0.62, z: 1.0, cy: 1.52, cz: HZ + 0.06 };
  if (opts.cap !== false) {
  const capG = new THREE.Group(); head.add(capG);
  if (opts.capBack) { capG.rotation.y = Math.PI; capG.position.z = 2 * CAP.cz; }      // casquette a l'envers (ado)
  const dome = new THREE.Mesh(new THREE.SphereGeometry(1, 40, 20, 0, Math.PI * 2, 0, Math.PI / 2), mat(C.cap));
  dome.scale.set(CAP.x, CAP.y, CAP.z); dome.castShadow = true; dome.receiveShadow = true;
  capG.add(at(dome, 0, CAP.cy, CAP.cz));
  capG.add(at(rbox(2.04, 0.12, 2.0, C.capDark, 0.05), 0, CAP.cy + 0.03, CAP.cz));      // bandeau
  const brim = at(rbox(1.74, 0.09, 0.95, C.capDark, 0.045), 0, CAP.cy + 0.02, FRONT + 0.33);
  brim.rotation.x = 0.07; capG.add(brim);
  const az = 0.55, el = 0.42;                                                            // badge pose sur le dome
  const n = new THREE.Vector3(Math.sin(az) * Math.cos(el) / CAP.x, Math.sin(el) / CAP.y, Math.cos(az) * Math.cos(el) / CAP.z).normalize();
  const bp = new THREE.Vector3(Math.sin(az) * Math.cos(el) * CAP.x, CAP.cy + Math.sin(el) * CAP.y, CAP.cz + Math.cos(az) * Math.cos(el) * CAP.z);
  if (opts.badge !== false) for (const [w, h, d, c, off] of [[0.46, 0.36, 0.06, C.badge, 0.0], [0.22, 0.17, 0.04, C.badgeInner, 0.035]]) {
    const b = rbox(w, h, d, c, 0.05, { roughness: 0.3, metalness: 0.35 });
    b.position.copy(bp).addScaledVector(n, off); b.lookAt(b.position.clone().add(n)); capG.add(b);
  }

  }
  root.userData.rig = { head, torso, ...arms, ...legs };
  root.userData.lenses = lenses;
  root.userData.wink = (k) => lenses.filter((m) => m.position.x > 0).forEach((m) => (m.scale.y = Math.max(0.08, 1 - k)));
  root.userData.height = 6.0;
  return root;
}

export function pose(shark, p = {}) {
  const r = shark.userData.rig;
  for (const k of ['armL', 'armR', 'legL', 'legR', 'head', 'torso']) {
    const v = p[k] || {};
    r[k].rotation.set(v.x || 0, v.y || 0, v.z || 0);
  }
}

export function walkPose(shark, t, speed = 1, amp = 0.75) {
  const ph = Math.sin(t * Math.PI * 2 * 1.6 * speed);
  pose(shark, {
    armL: { x: ph * amp }, armR: { x: -ph * amp },
    legL: { x: -ph * amp }, legR: { x: ph * amp },
    head: { x: 0.03 * Math.abs(ph) },
  });
  shark.userData.bob = Math.abs(ph) * 0.08;
}

export function talkPose(shark, t, intensity = 1) {
  const a = Math.sin(t * 9.0) * 0.05 * intensity, b = Math.sin(t * 2.3) * 0.08 * intensity;
  pose(shark, { head: { x: a, y: b }, armR: { x: -0.5 - Math.sin(t * 3.1) * 0.25 * intensity, z: 0.15 }, armL: { z: -0.05 } });
}

// Petit Shark : Docteur Shark ado (ep06). Plus petit, tete plus grosse, sweat gris, casquette a l'envers sans badge.
export function makePetitShark() {
  const s = makeDocShark({ headScale: 1.3, capBack: true, badge: false,
    colors: { hoodie: '#8a96a6', hoodieShade: '#77828f', jeans: '#3b4f74', shoe: '#e94b3c', sole: '#f4f6f8' } });
  s.name = 'PetitShark'; s.scale.setScalar(0.8); s.userData.height = 5.0;
  return s;
}

// Maman Shark : mere de Petit Shark (ep06). Sans casquette ni lunettes, yeux avec cils, gilet rose, jupe longue, collier.
export function makeMamanShark() {
  const s = makeDocShark({ headScale: 1.08, cap: false, glasses: false, lashes: true,
    colors: { skinDark: '#6f93a8', skinMid: '#7f9fb2', skinLight: '#a9c0cb', hoodie: '#d98fa6', hoodieShade: '#c47790', string: '#d98fa6', jeans: '#5b4a6e', shoe: '#3a2f45', sole: '#2a2232' } });
  s.name = 'MamanShark';
  const r = s.userData.rig;
  const hp = (m) => (m.geometry && m.geometry.parameters) || {};
  r.torso.children.filter((m) => [0.64, 0.14].some((h) => Math.abs((hp(m).height || 0) - h) < 1e-6) || Math.abs((hp(m).height || 0) - 0.55) < 1e-6).forEach((m) => (m.visible = false)); // cordons, noeuds, poche
  for (let i = 0; i < 9; i++) {                                                     // collier de perles, sous le menton
    const a = -1.0 + i * 0.25, pearl = new THREE.Mesh(new THREE.SphereGeometry(0.08, 12, 8), mat('#f6f1e6', { roughness: 0.25 }));
    pearl.position.set(Math.sin(a) * 0.62, 1.55 + (1 - Math.cos(a)) * 0.55, 0.53); pearl.castShadow = true; r.torso.add(pearl);
  }
  r.torso.add(at(rbox(0.06, 1.3, 0.05, '#c47790', 0.02), 0, 0.75, 0.52));          // ouverture du gilet
  for (let i = 0; i < 3; i++) r.torso.add(at(rbox(0.14, 0.14, 0.05, '#f6f1e6', 0.05), 0.14, 1.2 - i * 0.4, 0.535));
  const skirt = rbox(2.3, 1.5, 1.25, '#5b4a6e', 0.14); skirt.position.set(0, -0.55, 0); r.torso.add(skirt);   // jupe longue
  s.userData.height = 5.9;
  return s;
}
