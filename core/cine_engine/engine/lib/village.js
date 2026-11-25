// Monde persistant : le village, ses habitants et les accessoires. Chaque plan part de reset().
export function buildVillage(THREE, W, S) {
  const root = new THREE.Group();
  const at = (o, x, y, z, ry = 0) => { o.position.set(x, y, z); o.rotation.y = ry; return o; };
  const P = W.PAL;
  const add = (o) => { root.add(o); return o; };

  add(W.makeGround());
  const townhall = add(at(W.makeTownHall(), 0, 0, -30));
  const houseSpecs = [
    ['L1', -24, -16, Math.PI / 2, { wall: P.cream, roof: P.roofSlate, floors: 2, shutters: '#3f6f9f' }],
    ['L2', -24, -5, Math.PI / 2, { wall: P.butter, roof: P.roofTerra }],
    ['L3', -24, 6, Math.PI / 2, { wall: P.sky2, roof: P.roofBrown, floors: 2 }],
    ['L4', -24, 17, Math.PI / 2, { wall: P.rose, roof: P.roofSlate }],
    ['R1', 24, -16, -Math.PI / 2, { wall: P.mint, roof: P.roofTerra, floors: 2, shutters: '#2f6b4f' }],
    ['R2', 24, -5, -Math.PI / 2, { wall: P.cream, roof: P.roofBrown }],
    ['shark', 24, 6, -Math.PI / 2, { wall: P.brick, roof: '#e9eef3', door: '#24453a', floors: 2, w: 7 }],
    ['R4', 24, 17, -Math.PI / 2, { wall: P.butter, roof: P.roofSlate, floors: 2 }],
    ['B1', -15, -29, 0, { wall: P.rose, roof: P.roofBrown, floors: 2 }],
    ['B2', 15, -29, 0, { wall: P.sky2, roof: P.roofTerra, floors: 2, shutters: '#3f6f9f' }],
    ['F1', -15, 30, Math.PI, { wall: P.mint, roof: P.roofSlate }],
    ['F2', 15, 30, Math.PI, { wall: P.cream, roof: P.roofTerra, floors: 2 }],
  ];
  const houses = {};
  for (const [n, x, z, ry, o] of houseSpecs) houses[n] = add(at(W.makeHouse(o), x, 0, z, ry));
  const stallSpecs = [[-10, -9, 0.35, '#d94a3a'], [-4, -12, 0.1, '#2f6fd6'], [4, -12, -0.1, '#2e9e5b'], [10, -9, -0.35, '#d94a3a'], [-13, 5, 1.2, '#2f6fd6'], [13, 5, -1.2, '#e08a1e']];
  const stalls = stallSpecs.map(([x, z, ry, c]) => add(at(W.makeStall({ stripe: c }), x, 0, z, ry)));
  const fountain = add(at(W.makeFountain(), 0, 0, 0));
  for (const [x, z, s] of [[-31, -31, 1.3], [31, -31, 1.2], [-33, 25, 1.1], [33, 25, 1.3], [-6, 33, 1], [6, 33, 1.1], [-38, -8, 1.4], [38, -6, 1.3], [-36, 10, 1.2], [37, 12, 1.1], [-26, -38, 1.5], [26, -40, 1.4]]) add(at(W.makeTree({ scale: s }), x, 0, z));
  const lampObjs = [[-16, -13], [16, -13], [-16, 13], [16, 13], [19.5, 1.5], [19.5, 10.5]].map(([x, z]) => add(at(W.makeLamp(false), x, 0, z)));
  const lanterns = lampObjs.map((l) => l.children[1]);
  const banner = new THREE.Group(); add(at(banner, 0, 0, -15));
  for (const s of [-1, 1]) banner.add(at(W.makeLamp(false), s * 8, 0, 0));
  const bannerTex = W.canvasTex(1024, 180, (c, w, h) => { c.fillStyle = P.yellow; c.fillRect(0, 0, w, h); c.strokeStyle = '#1b1b1b'; c.lineWidth = 16; c.strokeRect(8, 8, w - 16, h - 16); c.fillStyle = '#d42b1e'; c.font = '900 120px Montserrat, Arial Black, sans-serif'; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText('TOUT À -50 %', w / 2, h / 2 + 8); });
  const bannerPlane = W.plane(14, 2.4, bannerTex, { double: true }); at(bannerPlane, 0, 5.6, 0); banner.add(bannerPlane);
  const mountain = add(at(W.makeMountain(), 0, 0, -230)); mountain.scale.setScalar(1.7);
  const ridge = add(at(W.makeMountain({ color: '#5f7a6c' }), -30, 0, -150)); ridge.scale.set(0.9, 0.75, 0.9);
  const castle = add(at(W.makeCastle(), 85, 0, -150));

  const shark = add(S.makeDocShark());
  const petitShark = add(S.makePetitShark()); const mamanShark = add(S.makeMamanShark());   // ep06
  // ep06 : ruelle a l'affiche (-150,320), cage d'escalier (-150,240), interieur de Petit Shark (-150,160 est la plonge ; on prend -150,400)
  const alley = add(at(W.makeAlley(), -150, 0, 320)); alley.visible = false;
  const stairwell = add(at(W.makeStairwell(), -150, 0, 240)); stairwell.visible = false;
  const sharkHome = add(at(W.makeSharkHome(), -150, 0, 400)); sharkHome.visible = false;
  const phone = W.makePhone(); phone.visible = false;
  const suitcase = add(W.makeSuitcase()); suitcase.visible = false;
  const noeBook = W.makeNotebook({ title: 'P. Shark', rows: [['12/11', '2 400 €'], ['15/11', '3 100 €'], ['19/11', '5 800 €'], ['Déclaré ?', '???']] }); noeBook.scale.setScalar(0.55); noeBook.visible = false;
  const noe = add(W.makeVillager({ name: 'noe', skin: '#d9a982', shirt: '#4b5361', pants: '#2a2f38', shoes: '#2b2b2b', hair: '#1c1410', hairStyle: 'spiky', hood: '#4b5361' })); noe.scale.setScalar(0.85); noe.userData.rig.armR.add(at(noeBook, 0, -2.2, 0.6)); noeBook.rotation.set(-0.9, 0, 0);
  const vSpecs = [
    { shirt: '#e0674f', pants: '#34495e', hair: '#3b2a20', hairStyle: 'flat' },
    { shirt: '#3f8fd2', pants: '#2c3e50', hair: '#d9a441', hairStyle: 'spiky', skin: '#f3d2b3' },
    { shirt: '#f2c14e', pants: '#6b4a3a', hair: '#e46a8a', hairStyle: 'puffy', skin: '#e9b98f' },
    { shirt: '#2fae7a', pants: '#283747', hair: '#1f1f1f', hairStyle: 'long', skin: '#c68b5e' },
    { shirt: '#9b59b6', pants: '#34495e', hair: '#8a5a2b', hairStyle: 'cap', cap: '#e74c3c', skin: '#f0c9a0' },
    { shirt: '#e67e22', pants: '#1c2833', hair: '#f2f2f2', hairStyle: 'bald', skin: '#e8c4a0', mustache: '#f2f2f2' },
    { shirt: '#ffffff', pants: '#2e86c1', hair: '#3b2a20', hairStyle: 'puffy', skin: '#8d5a3b', apron: '#d35400' },
    { shirt: '#c0392b', pants: '#212f3d', hair: '#f4d03f', hairStyle: 'flat', skin: '#f6d7b8', glasses: '#222' },
    { shirt: '#16a085', pants: '#5d4037', hair: '#5d3a1a', hairStyle: 'spiky', skin: '#d8a072' },
    { shirt: '#f78fb3', pants: '#3d3d6b', hair: '#2b1b14', hairStyle: 'long', skin: '#f0c9a0' },
  ];
  const villagers = vSpecs.map((v, i) => add(W.makeVillager({ ...v, name: 'v' + i })));
  const marcelOld = add(W.makeVillager({ name: 'marcelOld', skin: '#eac3a0', shirt: '#8a6a4a', pants: '#5a4a3a', shoes: '#3a2a1a', hair: '#f2f2f2', hairStyle: 'bald', beard: '#f2f2f2', glasses: '#3a3a3a' }));
  const cane = new THREE.Group(); cane.add(at(new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 2.2, 8), new THREE.MeshStandardMaterial({ color: '#6b4226', roughness: 0.6 })), 0, -1.1, 0));
  marcelOld.userData.rig.armR.add(at(cane, 0, -1.9, 0.35));
  const marcelRich = add(W.makeVillager({ name: 'marcelRich', skin: '#eac3a0', suit: '#1f2a44', tie: P.gold, chain: true, pants: '#1f2a44', shoes: '#111', hair: '#f2f2f2', hairStyle: 'bald', beard: '#f2f2f2', glasses: '#111' }));
  const bear = add(W.makeBear());
  bear.userData.eyes.forEach((e) => { e.material.fog = false; });
  const bearMats = []; bear.traverse((m) => { if (m.isMesh) bearMats.push([m, m.material]); });
  const goldCar = add(W.makeGoldCar());
  const card = W.makePassCard(); card.visible = false; shark.userData.rig.armR.add(at(card, 0, -2.25, 0.55)); card.rotation.x = -0.3;
  const gate = add(at(W.makeGate(), 0, 0, 38));
  const ticker = add(at(W.makeTicker(), 0, 9.5, -17));
  const priceBoard = new THREE.Group(); priceBoard.add(at(W.makePriceBoard(), 0, 5.2, 0));
  priceBoard.add(at(new THREE.Mesh(new THREE.BoxGeometry(0.25, 3.2, 0.25), new THREE.MeshStandardMaterial({ color: '#7a5236' })), 0, 1.6, -0.1));
  add(at(priceBoard, 0, 0, -6));
  const subscribe = add(W.makeSubscribe());
  const hat = new THREE.Group();
  hat.add(new THREE.Mesh(new THREE.CylinderGeometry(0.75, 0.75, 0.08, 20), new THREE.MeshStandardMaterial({ color: '#9a7a5c' })));
  hat.add(at(new THREE.Mesh(new THREE.CylinderGeometry(0.48, 0.5, 0.45, 20), new THREE.MeshStandardMaterial({ color: '#9a7a5c' })), 0, 0.25, 0));
  hat.add(at(new THREE.Mesh(new THREE.CylinderGeometry(0.505, 0.505, 0.1, 20), new THREE.MeshStandardMaterial({ color: '#3a2a20' })), 0, 0.1, 0));
  hat.traverse((m) => { if (m.isMesh) { m.castShadow = true; m.receiveShadow = true; } });
  add(hat);
  const looseCane = add(new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 2.2, 8), new THREE.MeshStandardMaterial({ color: '#a0703f' })));
  const coinGeo = new THREE.CylinderGeometry(0.32, 0.32, 0.08, 20);
  const coinMat = new THREE.MeshStandardMaterial({ color: P.gold, metalness: 0.9, roughness: 0.25, emissive: '#b8860b', emissiveIntensity: 0.65 });
  const coins = new THREE.InstancedMesh(coinGeo, coinMat, 90); coins.castShadow = true; add(coins);
  const snowGeo = new THREE.BufferGeometry(); const NS = 1400; const snowBase = new Float32Array(NS * 3);
  for (let i = 0; i < NS; i++) { snowBase[i * 3] = (Math.sin(i * 12.9898) * 43758.5453 % 1) * 40 - 20; snowBase[i * 3 + 1] = (Math.sin(i * 78.233) * 12345.678 % 1 + 1) * 12; snowBase[i * 3 + 2] = (Math.sin(i * 39.425) * 24634.6345 % 1) * 40 - 20; }
  snowGeo.setAttribute('position', new THREE.BufferAttribute(snowBase.slice(), 3));
  const snow = add(new THREE.Points(snowGeo, new THREE.PointsMaterial({ color: '#ffffff', size: 0.14, transparent: true, opacity: 0.9, depthWrite: false })));

  // --- ep02 : banque (a la place de la mairie), moulin + champ (hors village, x=100), chambre de Lea et atelier de frappe (interieurs, x=-150)
  const bank = add(at(W.makeBank(), 0, 0, -30));
  const mill = add(at(W.makeMill(), 112, 0, 24, -0.5));
  const field = add(at(W.makeField(), 100, 0, 42));
  for (const [x, z, s] of [[84, 30, 1.3], [88, 56, 1.1], [124, 50, 1.4], [120, 12, 1.2], [96, 14, 1.0]]) add(at(W.makeTree({ scale: s }), x, 0, z));
  const bedroom = add(at(W.makeBedroom(), -150, 0, 0));
  const coinpress = add(at(W.makeCoinPress(), -150, 0, 80));
  const lea = add(W.makeVillager({ name: 'lea', skin: '#f3d2b3', shirt: '#3aa6a0', pants: '#2c3e50', shoes: '#5a3a2a', hair: '#b5472b', hairStyle: 'long' }));
  const sharkCoin = W.makeCoin(); sharkCoin.scale.setScalar(1.6); sharkCoin.visible = false; shark.userData.rig.armR.add(at(sharkCoin, 0, -2.3, 0.5));
  const leaCoin = W.makeCoin(); leaCoin.scale.setScalar(1.4); leaCoin.visible = false; lea.userData.rig.armR.add(at(leaCoin, 0, -2.15, 0.45));
  // --- ep03 : boutique du marchand (a la place de la mairie), maman, marchand, tirelire, carnet, plonge, bonnet, sacs
  const shop = add(at(W.makeShop(), 0, 0, -30));
  const mom = add(W.makeVillager({ name: 'mom', skin: '#efc8a6', shirt: '#8d8f96', pants: '#4a4e57', shoes: '#3a2a1a', hair: '#7a4a2a', hairStyle: 'long', shawl: '#a7a39a' }));
  const momCoat = add(W.makeVillager({ name: 'momCoat', skin: '#efc8a6', shirt: '#8d8f96', pants: '#4a4e57', shoes: '#3a2a1a', hair: '#7a4a2a', hairStyle: 'long', coat: '#c62828' }));
  const merchant = add(W.makeVillager({ name: 'merchant', skin: '#e6b48c', shirt: '#2c2c34', pants: '#2c2c34', shoes: '#111', hair: '#1f1f1f', hairStyle: 'flat', mustache: '#1f1f1f', apron: '#d42b1e' }));
  // ep07 : le pere (bleu de travail, moustache) et la voisine d'en face
  const papa = add(W.makeVillager({ name: 'papa', skin: '#e6b48c', shirt: '#2f4f8f', pants: '#2f4f8f', shoes: '#2b2b2b', hair: '#3b2a20', hairStyle: 'flat', mustache: '#3b2a20' }));
  const voisine = add(W.makeVillager({ name: 'voisine', skin: '#f0c9a0', shirt: '#b0306a', pants: '#2d2d3a', shoes: '#111111', hair: '#1a1a1a', hairStyle: 'long' }));
  const piggy = add(W.makePiggyBank());
  const notebook = add(W.makeNotebook());
  const dishes = add(at(W.makeDishes(), -150, 0, 160));
  const bonnet = add(W.makeBonnet());
  const leaBags = [W.makeBag('#e8d5b0'), W.makeBag('#d9a6c9')]; lea.userData.rig.armL.add(at(leaBags[0], 0, -2.1, 0.1)); lea.userData.rig.armR.add(at(leaBags[1], 0, -2.1, 0.1));
  const leaPiggy = W.makePiggyBank(); leaPiggy.scale.setScalar(0.8); lea.userData.rig.armR.add(at(leaPiggy, 0, -2.6, 0.5)); leaPiggy.rotation.x = -Math.PI / 2;
  const sharkBook = W.makeNotebook(); sharkBook.scale.setScalar(0.9); shark.userData.rig.armR.add(at(sharkBook, 0, -2.3, 0.7)); sharkBook.rotation.set(-0.9, 0, 0);
  // --- ep05 : compteurs de vie au poignet, gros plan de poignet, jetons-parts, boulangerie, narrateur (villageois 1)
  const bakery = add(at(W.makeBakery(), -6, 0, -11, 0.25)); bakery.visible = false;
  const bigWrist = add(W.makeBigWrist()); bigWrist.visible = false;
  const wrists = new Map();
  const wristOn = (a, side = 'armL') => { const m = W.makeWristClock(); m.scale.setScalar(0.82); m.position.set(0, -1.42, 0.49); a.userData.rig[side].add(m); m.visible = false; wrists.set(a, m); return m; };
  [shark, mom, merchant, ...villagers].forEach((a) => wristOn(a));
  const badges = W.makeTokenBadges(); shark.userData.rig.torso.add(badges); badges.visible = false;
  const narrBadges = W.makeTokenBadges(); villagers[1].userData.rig.torso.add(narrBadges); narrBadges.visible = false;
  const movable = [bigWrist, shark, petitShark, mamanShark, noe, ...villagers, marcelOld, marcelRich, bear, lea, mom, momCoat, merchant, papa, voisine, piggy, notebook, bonnet, goldCar, subscribe, hat, looseCane, priceBoard, ticker, gate, snow, coins];
  const defaults = new Map(movable.map((o) => [o, { p: o.position.clone(), r: o.rotation.clone(), s: o.scale.clone() }]));
  const nightGlass = new THREE.MeshStandardMaterial({ color: P.windowNight, emissive: P.windowNight, emissiveIntensity: 1.4 });
  const glassList = [];
  Object.values(houses).forEach((h) => h.userData.windows.forEach((wg) => glassList.push({ m: wg.children[1], day: wg.children[1].material })));
  const lanternMat = new THREE.MeshStandardMaterial({ color: '#ffe3a0', emissive: '#ffcf6b', emissiveIntensity: 0 });
  lanterns.forEach((l) => (l.material = lanternMat));
  banner.children.forEach((c) => { if (c.children[1]) c.children[1].material = lanternMat; });
  let coinRain = null, snowOn = false, talker = null, rainOn = false;
  const actors = [shark, petitShark, mamanShark, noe, ...villagers, marcelOld, marcelRich, bear, lea, mom, momCoat, merchant, papa, voisine];

  function poseAll(actor, p = {}) {
    const r = actor.userData.rig;
    for (const k of ['armL', 'armR', 'legL', 'legR', 'head', 'torso']) { const v = p[k] || {}; if (r[k]) r[k].rotation.set(v.x || 0, v.y || 0, v.z || 0); }
    if (r.jaw) r.jaw.rotation.set((p.jaw && p.jaw.x) || 0, 0, 0);
  }

  const api = {
    papa, voisine, bakery, bigWrist, wrists, badges, narrBadges, wrist: (a) => wrists.get(a),
    root, petitShark, mamanShark, noe, alley, stairwell, sharkHome, phone, suitcase, noeBook, houses, stalls, shop, mom, momCoat, merchant, piggy, notebook, dishes, bonnet, leaBags, leaPiggy, sharkBook, sharkCoin, leaCoin, bank, mill, field, bedroom, coinpress, lea, townhall, fountain, banner, mountain, ridge, castle, shark, villagers, marcelOld, marcelRich, bear, goldCar, card, gate, ticker, priceBoard, subscribe, hat, looseCane, coins, snow,
    reset() {
      for (const [o, d] of defaults) { o.position.copy(d.p); o.rotation.copy(d.r); o.scale.copy(d.s); }
      for (const a of [shark, petitShark, mamanShark, noe, ...villagers, marcelOld, marcelRich, bear, lea, mom, momCoat, merchant, papa, voisine]) { a.visible = false; poseAll(a); if (a.userData.setExpr) a.userData.setExpr('neutral'); }
      petitShark.userData.wink(0); shark.userData.wink(0); noeBook.rotation.set(-0.9, 0, 0); sharkHome.userData.light.intensity = 12; sharkHome.userData.light.color.set('#ffe0b0'); sharkHome.userData.lampMat.emissiveIntensity = 1.4; 
      for (const o of [alley, stairwell, sharkHome, phone, suitcase, noeBook]) o.visible = false; if (phone.parent) phone.parent.remove(phone); stairwell.userData.setLamp(true); stairwell.userData.door.rotation.y = 0; alley.userData.poster.userData.draw(false); phone.userData.glow.intensity = 0; rainOn = false; snow.material.color.set('#ffffff'); snow.material.size = 0.14;
      for (const o of [goldCar, subscribe, hat, looseCane, priceBoard, ticker, snow, coins]) o.visible = false;
      card.visible = false; card.rotation.set(-0.3, 0, 0); cane.visible = true; banner.visible = true; gate.visible = true; castle.visible = true;
      if (subscribe.parent !== root) root.add(subscribe);
      Object.values(houses).forEach((h) => (h.userData.door.rotation.y = 0));
      gate.userData.doors.forEach((d) => (d.rotation.y = 0));
      bear.userData.eyes.forEach((e) => (e.material.emissiveIntensity = 2.5));
      bearMats.forEach(([m, mt]) => { m.material = mt; if (!bear.userData.eyes.includes(m)) { mt.transparent = false; mt.opacity = 1; } });
      priceBoard.children[0].userData.draw('100 €', false);
      bank.visible = false; townhall.visible = true; sharkCoin.visible = false; leaCoin.visible = false; bank.userData.drawClock(0); bank.userData.tickSmoke(0, false);
      bank.userData.doors.forEach((d) => (d.rotation.y = 0)); bank.userData.inner.material.emissiveIntensity = 0;
      mill.userData.blades.rotation.z = 0; field.userData.grow(0);
      bedroom.userData.mattress.rotation.z = 0; bedroom.userData.coins.children.forEach((c) => { c.scale.setScalar(1); c.visible = true; });
      coinpress.userData.ram.position.y = 3.6; coinpress.userData.fillPile(0.4);
      ticker.userData.drawChart(1);
      shop.visible = false; piggy.visible = false; notebook.visible = false; bonnet.visible = false; dishes.visible = false; leaBags.forEach((b) => (b.visible = false)); leaPiggy.visible = false; sharkBook.visible = false;
      shop.userData.promoPivot.rotation.set(0, 0, 0); notebook.userData.draw(0); sharkBook.userData.draw(0); bonnet.userData.halves.forEach((h) => h.rotation.set(0, 0, 0)); bonnet.userData.pom.position.set(0, 0.82, 0);
      bakery.visible = false; bigWrist.visible = false; wrists.forEach((m) => { m.visible = false; m.userData.last = null; }); badges.visible = false; narrBadges.visible = false; badges.userData.setCount(15); narrBadges.userData.setCount(15); badges.userData.glow(0.5);
      coins.count = 0; coinRain = null; snowOn = false; talker = null;
    },
    // v3.4 : personnages vivants (clignement, respiration, bouche sur la voix). Appele par film.html a chaque image.
    talk(a) { talker = a; },
    life(t, tg, speaking) {
      actors.forEach((a, i) => {
        if (!a.visible) return;
        const r = a.userData.rig;
        if (r && r.torso && !a.userData.noBreath) r.torso.scale.y = 1 + 0.012 * Math.sin(tg * 2.1 + i);
        if (!a.userData.setFace) return;
        const ph = (tg + i * 1.37) % 3.7;                 // un clignement toutes les 3,7 s, decale par personnage
        const blink = ph < 0.12;
        const open = a === talker && speaking && Math.sin(tg * 2 * Math.PI * 4.2) > -0.2;
        a.userData.setFace((blink ? 'b' : '') + (open ? 'o' : ''));
      });
      if (talker && talker.userData.rig && talker.userData.rig.jaw) talker.userData.rig.jaw.rotation.x = speaking ? 0.12 * Math.max(0, Math.sin(tg * 2 * Math.PI * 4.2)) : 0;
    },
    setNight(on) {
      glassList.forEach((g) => (g.m.material = on ? nightGlass : g.day));
      lanternMat.emissiveIntensity = on ? 1.8 : 0;
    },
    pose: poseAll,
    show(...objs) { objs.forEach((o) => (o.visible = true)); },
    place(o, x, z, ry = 0, y = 0) { o.position.set(x, y, z); o.rotation.y = ry; o.visible = true; return o; },
    walk(a, from, to, t0, t1, t, o = {}) {
      const k = Math.min(1, Math.max(0, (t - t0) / Math.max(0.001, t1 - t0)));
      const x = from[0] + (to[0] - from[0]) * k, z = from[1] + (to[1] - from[1]) * k;
      const moving = k > 0 && k < 1;
      a.position.set(x, o.y || 0, z);
      a.rotation.y = o.face !== undefined ? o.face : Math.atan2(to[0] - from[0], to[1] - from[1]);
      const sp = o.speed || 1, amp = o.amp || 0.7;
      const ph = moving ? Math.sin(t * Math.PI * 2 * 1.7 * sp) : 0;
      poseAll(a, { armL: { x: ph * amp }, armR: { x: -ph * amp }, legL: { x: -ph * amp }, legR: { x: ph * amp }, ...(o.pose || {}) });
      a.position.y += moving ? Math.abs(ph) * 0.1 : 0;
      return k;
    },
    coinRain(cx, cz, t0) { coinRain = { cx, cz, t0 }; coins.visible = true; },
    snowOn(cx, cz) { snowOn = { cx, cz }; snow.visible = true; },
    rainOn(cx, cz) { snowOn = { cx, cz }; rainOn = true; snow.visible = true; snow.material.color.set('#9fb6d6'); snow.material.size = 0.09; },   // ep06 : pluie
    tick(t) {
      if (coinRain) {
        const m = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler();
        const n = Math.min(90, Math.floor((t - coinRain.t0) * 40));
        coins.count = Math.max(0, n);
        for (let i = 0; i < coins.count; i++) {
          const born = coinRain.t0 + i / 40, age = t - born;
          const x = coinRain.cx + Math.sin(i * 7.31) * 4.5, z = coinRain.cz + Math.cos(i * 3.17) * 3.0;
          const y = Math.max(0.05, 14 - age * age * 9.8 * 0.6);
          e.set(age * 6 + i, age * 3, Math.PI / 2 + (y <= 0.05 ? 0 : age * 4)); q.setFromEuler(e);
          m.compose(new THREE.Vector3(x, y, z), q, new THREE.Vector3(1, 1, 1)); coins.setMatrixAt(i, m);
        }
        coins.instanceMatrix.needsUpdate = true;
      }
      if (snowOn) {
        const pos = snow.geometry.attributes.position;
        for (let i = 0; i < NS; i++) {
          pos.array[i * 3] = snowOn.cx + snowBase[i * 3] + Math.sin(t * 0.8 + i) * 0.4;
          pos.array[i * 3 + 1] = ((snowBase[i * 3 + 1] - t * (rainOn ? 16 : 1.4)) % 12 + 12) % 12;
          pos.array[i * 3 + 2] = snowOn.cz + snowBase[i * 3 + 2];
        }
        pos.needsUpdate = true;
      }
    },
  };
  return api;
}
