// EXTRAIT de l'episode 1 (13 plans sur 27) : modeles de plans a reprendre. Episode 1 : « Dans ce village, l'Ours revient tous les 10 ans »
// Chaque plan = une phrase ou un morceau de phrase de la narration (timeline.json).
export function buildShots(ctx) {
  const { world: w, timeline: T, lamps, cam } = ctx;
  const line = (id) => T.lines.find((l) => l.id === id);
  const chunk = (id, k) => line(id).chunks[k].start;
  const sharkHouseDoor = [21.46, 6.0];
  const face = (x, z, tx, tz) => Math.atan2(tx - x, tz - z);
  const osc = (t, f, a) => Math.sin(t * f) * a;
  const shoutPose = (t, ph = 0) => ({ armR: { z: 2.5 + osc(t + ph, 9, 0.35) }, armL: { z: -2.3 - osc(t + ph, 8, 0.35) }, head: { x: osc(t + ph, 7, 0.06) } });
  const laughPose = (t, ph = 0) => ({ head: { z: osc(t + ph, 14, 0.12), x: -0.15 }, torso: { x: osc(t + ph, 14, 0.04) }, armL: { x: -0.7, z: 0.35 }, armR: { x: -1.5, z: -0.1 } });
  const bearGiant = (x, y, z, s) => { w.place(w.bear, x, z, 0, y); w.bear.scale.setScalar(s); };
  const fadeBear = (alpha) => w.bear.traverse((m) => { if (m.isMesh && !w.bear.userData.eyes.includes(m)) { m.material.transparent = true; m.material.opacity = alpha; } });
  const darkBear = () => w.bear.traverse((m) => { if (m.isMesh && !w.bear.userData.eyes.includes(m)) { m.material = m.material.clone(); m.material.fog = false; m.material.color.multiplyScalar(0.5); } });

  const S = [
    { name: 's01_village_aerien', start: 0, preset: 'day',
      setup: (c) => { c.shadowFocus(0, -5, 45); c.camera({ pos: [0, 44, 50], target: [0, 0, -6], fov: 46 }, { pos: [0, 30, 33], target: [0, 1, -9], fov: 44 }); },
      update: (c, t) => { w.stalls.forEach((s, i) => (s.userData.sign.rotation.z = osc(t + i, 2.2, 0.05))); } },
    { name: 's03_ours_montagne', start: line('L3').start, preset: 'overcast',
      setup: (c) => { c.scene.fog.near = 30; c.scene.fog.far = 240; c.shadowFocus(-10, -20, 40); bearGiant(-30, -48, -172, 6.0); darkBear(); c.camera({ pos: [-10, 18, 0], target: [-30, 32, -150], fov: 40 }, { pos: [-11, 18.5, -14], target: [-31, 36, -150], fov: 33 }); },
      update: (c, t, p) => {
        const rise = c.ease.out(Math.min(1, p * 1.25)); w.bear.position.y = -48 + rise * 38;
        const tO = c.wordTime('ours') ?? 3.0; const glow = t > tO - 0.2 ? 2.5 + osc(t, 20, 0.6) + 2 : 0.6;
        w.bear.userData.eyes.forEach((e) => (e.material.emissiveIntensity = glow));
        w.pose(w.bear, { armL: { x: -0.4, z: -0.3 }, armR: { x: -0.4, z: 0.3 }, head: { x: -0.1 } });
        c.shake(t > tO ? 0.06 : 0);
      } },
    { name: 's04a_prix_chutent', start: line('L4').start, preset: 'overcast',
      setup: (c) => { c.shadowFocus(0, -6, 15); w.priceBoard.visible = true; c.camera({ pos: [0, 5.2, 8.5], target: [0, 5.2, -6], fov: 36 }, { pos: [0, 5.2, 7.0], target: [0, 5.15, -6], fov: 36 }); },
      update: (c, t) => {
        const tE = c.wordTime('effondrent') ?? 1.0, b = w.priceBoard.children[0];
        const v = t < tE - 0.15 ? ['100 €', false] : t < tE + 0.35 ? ['50 €', true] : ['20 €', true];
        if (b.userData.last !== v[0]) { b.userData.draw(v[0], v[1]); b.userData.last = v[0]; }
        c.shake(t > tE - 0.15 && t < tE + 0.9 ? 0.05 : 0);
      } },
    { name: 's04b_tout_le_monde_senferme', start: chunk('L4', 2), preset: 'overcast',
      setup: (c) => {
        c.shadowFocus(-16, 0, 25);
        w.houses.L2.userData.door.rotation.y = -1.3; w.houses.L3.userData.door.rotation.y = -1.3;
        [w.villagers[0], w.villagers[2], w.villagers[8]].forEach((v) => { v.visible = true; v.userData.setExpr('shocked'); });
        c.camera({ pos: [-1.5, 6.2, 15], target: [-19, 2.6, 1], fov: 48 }, { pos: [-3.0, 5.8, 13.5], target: [-19, 2.6, 0.5], fov: 46 });
      },
      update: (c, t, p) => {
        const runs = [[w.villagers[0], [-11, -1], [-20.6, -5], 0, 0.9, 'L2'], [w.villagers[2], [-12, 8], [-20.6, 6], 0.1, 1.1, 'L3'], [w.villagers[8], [-8, 3], [-20.6, 6.4], 0.4, 1.5, 'L3']];
        for (const [v, a, b, t0, t1, h] of runs) {
          const k = w.walk(v, a, b, t0, t1, t, { speed: 1.8, amp: 1.0 });
          v.visible = k < 1;
        }
        const closeL2 = Math.min(1, Math.max(0, (t - 1.0) / 0.25)), closeL3 = Math.min(1, Math.max(0, (t - 1.6) / 0.25));
        w.houses.L2.userData.door.rotation.y = -1.3 * (1 - closeL2); w.houses.L3.userData.door.rotation.y = -1.3 * (1 - closeL3);
      } },
    { name: 's05_sauf_docteur_shark', start: line('L5').start, preset: 'overcast', flash: true,
      setup: (c) => { c.shadowFocus(19, 6, 15); w.shark.visible = true; c.camera({ pos: [9.4, 1.8, 11.6], target: [20.2, 3.9, 6.0], fov: 46 }, { pos: [10.4, 1.9, 11.0], target: [19.6, 4.1, 6.0], fov: 44 }); },
      update: (c, t) => {
        const tS = c.wordTime('sauf') ?? 1.2;
        const open = Math.min(1, Math.max(0, (t - (tS - 0.8)) / 0.4)); w.houses.shark.userData.door.rotation.y = -1.45 * c.ease.out(open);
        const k = w.walk(w.shark, [22.3, 6.0], [18.9, 6.0], tS - 0.5, tS + 1.1, t, { face: -Math.PI / 2, speed: 1.1 });
        if (k >= 1) w.pose(w.shark, { armR: { z: 0.5, x: -0.2 }, armL: { z: -0.5, x: -0.2 }, head: { y: -0.35, x: -0.05 } });
      } },
    { name: 's06b_marcel_part', start: chunk('L6', 1), preset: 'fog', post: 'sepia',
      setup: (c) => { c.shadowFocus(0, 0, 25); w.marcelOld.visible = true; c.camera({ pos: [7.6, 3.5, 18], target: [6, 3.0, -20], fov: 40 }, { pos: [7.3, 3.4, 15.5], target: [6, 3.0, -20], fov: 40 }); },
      update: (c, t) => { w.walk(w.marcelOld, [6.2, 8], [6.0, -6], 0, 3.2, t, { speed: 0.7, amp: 0.4, pose: { armR: { x: -0.25 } } }); } },
    { name: 's08_le_pass_broker', start: line('L8').start, preset: 'overcast',
      setup: (c) => { c.shadowFocus(10, 6, 12); w.place(w.shark, 10, 6, 0); w.card.visible = true; w.card.rotation.set(1.25, 0, 0); c.camera({ pos: [11.2, 4.9, 18.5], target: [10.2, 4.2, 6], fov: 38 }, { pos: [10.9, 4.8, 16.5], target: [10.2, 4.3, 6], fov: 36 }); },
      update: (c, t) => {
        const up = c.ease.out(Math.min(1, Math.max(0, (t - 0.3) / 0.6)));
        w.pose(w.shark, { armR: { x: -1.35 * up, z: -0.38 * up }, armL: { z: -0.12 }, head: { x: 0.05, y: 0.2 * up, z: -0.08 * up } });
        const tB = c.wordTime('broker') ?? 2.5; const glow = t > tB - 0.1 ? 0.35 + Math.max(0, 1.2 - (t - tB) * 2) : 0.35;
        w.card.children[0].material[4].emissiveIntensity = glow;
      } },
    { name: 's13_on_frappe_a_sa_porte', start: line('L13').start, preset: 'night',
      setup: (c) => {
        c.shadowFocus(20, 6, 15); w.snowOn(18, 6);
        lamps[0].position.set(19.6, 4.6, 4.2); lamps[0].intensity = 14; lamps[1].position.set(14, 5, 10); lamps[1].intensity = 8;
        c.camera({ pos: [10.8, 3.6, 11.6], target: [21.4, 4.6, 6.0], fov: 46 }, { pos: [12.6, 3.3, 10.4], target: [21.4, 4.2, 6.0], fov: 44 });
      },
      update: (c, t) => {
        const tF = c.wordTime('frappe') ?? 1.8; const d = w.houses.shark.userData.door;
        let j = 0; for (let n = 0; n < 3; n++) { const tk = tF + n * 0.28; if (t > tk && t < tk + 0.1) j = 0.035; }
        d.rotation.y = -j;
      } },
    { name: 's14_abonne_toi', start: line('L14').start, preset: 'night',
      setup: (c) => {
        c.shadowFocus(18, 6, 12); w.snowOn(16, 7);
        lamps[0].position.set(19.6, 4.6, 4.2); lamps[0].intensity = 14; lamps[1].position.set(13.5, 5.5, 9.5); lamps[1].intensity = 16;
        w.place(w.shark, 18.2, 6.6, face(18.2, 6.6, 10.6, 9.6));
        cam.add(w.subscribe); w.subscribe.visible = true; w.subscribe.position.set(0, -2.15, -8); w.subscribe.scale.setScalar(0.001);
        c.camera({ pos: [9.6, 5.4, 10.0], target: [18.2, 4.0, 6.6], fov: 42 }, { pos: [10.2, 5.3, 9.8], target: [18.2, 4.1, 6.6], fov: 41 });
      },
      update: (c, t) => {
        const k = Math.min(1, Math.max(0, (t - 0.15) / 0.3)); const s = k < 1 ? c.ease.out(k) * 1.15 : 1 + Math.max(0, 0.15 - (t - 0.45) * 0.6);
        w.subscribe.scale.setScalar(0.5 * Math.max(0.001, Math.min(1.15, s)));
        w.pose(w.shark, { armR: { x: -1.1, z: -0.5 + osc(t, 6, 0.06) }, head: { x: 0.12 + osc(t, 9, 0.04), y: osc(t, 2.5, 0.08) } });
      } },
    { name: 's15b_marcel_vivant', start: chunk('L15', 2), preset: 'night', flash: true,
      setup: (c) => {
        c.shadowFocus(18, 6, 15); w.snowOn(17, 6); w.houses.shark.userData.door.rotation.y = -1.45;
        lamps[0].position.set(20.4, 4.8, 7.8); lamps[0].intensity = 22; lamps[1].position.set(15, 5, 11); lamps[1].intensity = 14;
        w.place(w.marcelRich, 19.0, 6.6, face(19.0, 6.6, 14.8, 11.4)); w.marcelRich.userData.setExpr('smile');
        c.camera({ pos: [14.8, 4.9, 11.4], target: [19.0, 4.6, 6.6], fov: 40 }, { pos: [15.4, 4.8, 10.8], target: [19.0, 4.7, 6.6], fov: 37 });
      },
      update: (c, t) => { w.pose(w.marcelRich, { armR: { x: -1.6 + osc(t, 3, 0.1), z: -0.6 }, head: { z: osc(t, 2, 0.05), x: -0.05 } }); } },
    { name: 's18a_le_plus_riche', start: line('L18').start, preset: 'golden',
      setup: (c) => {
        c.shadowFocus(0, 6, 15); w.place(w.marcelRich, 0, 8, 0); w.marcelRich.userData.setExpr('laugh'); w.place(w.goldCar, -4.6, 3.6, 0.5);
        w.coinRain(0, 7.6, 0.2);
        c.camera({ pos: [3.2, 4.3, 24], target: [0, 3.8, 7], fov: 40 }, { pos: [2.6, 4.1, 21], target: [0, 4.0, 7], fov: 40 });
      },
      update: (c, t) => { w.pose(w.marcelRich, { armL: { z: -1.0 + osc(t, 5, 0.1) }, armR: { z: 1.0 - osc(t, 5, 0.1) }, head: { x: -0.12, z: osc(t, 12, 0.06) } }); } },
    { name: 's19a_le_vrai_monstre', start: line('L19').start, preset: 'overcast',
      setup: (c) => { c.scene.fog.near = 30; c.scene.fog.far = 240; c.shadowFocus(-10, -20, 40); bearGiant(-30, -10, -172, 6.0); darkBear(); c.camera({ pos: [-11, 18.5, -14], target: [-31, 36, -150], fov: 33 }, { pos: [-11, 18.5, -8], target: [-31, 34, -150], fov: 36 }); },
      update: (c, t, p) => {
        const k = c.ease.inOut(Math.min(1, Math.max(0, (p - 0.35) / 0.6)));
        w.bear.position.y = -10 - k * 36; fadeBear(1 - k * 0.85);
        w.bear.userData.eyes.forEach((e) => (e.material.emissiveIntensity = 3.5 * (1 - k)));
      } },
    { name: 's20b_wall_street', start: chunk('L20', 1), preset: 'overcast',
      setup: (c) => {
        c.shadowFocus(0, -10, 20); w.ticker.visible = true; w.banner.visible = false;
        [[3, -3.2, -8.6], [4, 0.4, -9.3], [6, 3.6, -8.4]].forEach(([i, x, z]) => { w.place(w.villagers[i], x, z, Math.PI + x * 0.03); });
        c.camera({ pos: [0, 6.8, 7], target: [0, 9.4, -17], fov: 46 }, { pos: [0, 7.6, 1.5], target: [0, 9.6, -17], fov: 44 });
      },
      update: (c, t, p) => {
        w.ticker.userData.drawChart(Math.min(1, 0.15 + p * 1.2));
        [3, 4, 6].forEach((i, k) => w.pose(w.villagers[i], { head: { x: -0.25, z: osc(t, 1.5 + k, 0.05) } }));
      } },
  ];
  for (let i = 0; i < S.length; i++) S[i].end = i + 1 < S.length ? S[i + 1].start : T.duration;
  return S;
}
