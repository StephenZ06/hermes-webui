// Office mesh builders — desks, chairs, people, nameplates (phase 3).
//
// Everything here is procedural: there are no models to load, so the office
// costs one vendored library and nothing else over the wire. Geometries and
// materials are cached and shared, because a busy run puts a few dozen of
// these on the floor and each unique geometry is a separate GPU upload.
//
// Written against the office's own needs rather than copied from the
// agents-office reference (PolyForm Noncommercial; this repo is MIT) — see
// the Licensing section of docs/rfcs/office-visualization.md.
//
// Every builder returns a THREE.Object3D. Callers own disposal; `disposeTree`
// releases anything a builder allocated that is not in the shared caches.
import * as THREE from 'three';

const _materials = new Map();
const _geometries = new Map();

/** Shared standard material, keyed by colour and finish. */
export function material(color, opts) {
  const options = opts || {};
  const key = `${color}|${options.rough ?? 0.85}|${options.metal ?? 0.02}|${options.emissive || ''}|${options.ei ?? 0}`;
  let mat = _materials.get(key);
  if (!mat) {
    mat = new THREE.MeshStandardMaterial(Object.assign({
      color,
      roughness: options.rough ?? 0.85,
      metalness: options.metal ?? 0.02,
    }, options.emissive ? { emissive: options.emissive, emissiveIntensity: options.ei ?? 1 } : {}));
    _materials.set(key, mat);
  }
  return mat;
}

function geometry(key, build) {
  let geo = _geometries.get(key);
  if (!geo) {
    geo = build();
    _geometries.set(key, geo);
  }
  return geo;
}

function box(w, h, d, color) {
  const mesh = new THREE.Mesh(
    geometry(`box|${w}|${h}|${d}`, () => new THREE.BoxGeometry(w, h, d)),
    typeof color === 'string' ? material(color) : color,
  );
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  return mesh;
}

function cylinder(rTop, rBottom, h, segments, color) {
  const mesh = new THREE.Mesh(
    geometry(`cyl|${rTop}|${rBottom}|${h}|${segments}`,
      () => new THREE.CylinderGeometry(rTop, rBottom, h, segments)),
    typeof color === 'string' ? material(color) : color,
  );
  mesh.castShadow = true;
  return mesh;
}

function capsule(radius, length, color) {
  const mesh = new THREE.Mesh(
    geometry(`cap|${radius}|${length}`, () => new THREE.CapsuleGeometry(radius, length, 3, 8)),
    typeof color === 'string' ? material(color) : color,
  );
  mesh.castShadow = true;
  return mesh;
}

/* ---------- pod plinth ---------- */

/**
 * The raised slab a cluster of desks sits on. Gives a pod a visible edge so
 * a delegation branch reads as one team rather than scattered furniture.
 */
export function makePod(width, depth, palette) {
  const group = new THREE.Group();
  const slab = box(width, 0.6, depth, palette.podTop);
  slab.position.y = 0.3;
  slab.castShadow = false;
  group.add(slab);
  const skirt = box(width - 0.8, 0.5, depth - 0.8, palette.podSide);
  skirt.position.y = -0.15;
  group.add(skirt);
  return group;
}

/* ---------- desk ---------- */

/**
 * Desk with a monitor whose screen is a live canvas texture — that screen is
 * where a worker's current tool call shows up.
 *
 * @returns {THREE.Group} with `userData.screen` = {canvas, ctx, texture}
 */
export function makeDesk(palette) {
  const group = new THREE.Group();

  const top = box(4.4, 0.2, 2.4, palette.deskTop);
  top.position.y = 1.5;
  group.add(top);

  [-1.9, 1.9].forEach(x => {
    const leg = box(0.25, 1.5, 2.0, palette.deskLeg);
    leg.position.set(x, 0.75, 0);
    group.add(leg);
  });

  const screen = makeScreen(palette);
  screen.position.set(0, 2.5, -0.7);
  group.add(screen);
  group.userData.screen = screen.userData.screen;

  const stand = cylinder(0.12, 0.2, 0.5, 8, palette.deskLeg);
  stand.position.set(0, 1.85, -0.7);
  group.add(stand);

  return group;
}

/** Monitor panel. Its canvas texture is redrawn by `drawScreen`. */
function makeScreen(palette) {
  const group = new THREE.Group();

  const bezel = box(2.9, 1.8, 0.12, palette.screenBezel);
  group.add(bezel);

  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 160;
  const ctx = canvas.getContext('2d');
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;

  const panel = new THREE.Mesh(
    new THREE.PlaneGeometry(2.7, 1.6),
    new THREE.MeshBasicMaterial({ map: texture, transparent: true }),
  );
  panel.position.z = 0.07;
  group.add(panel);

  // Not shared: this pair belongs to one desk and is disposed with it.
  group.userData.screen = { canvas, ctx, texture, panelGeometry: panel.geometry, panelMaterial: panel.material };
  return group;
}

/**
 * Repaint a desk screen. Text is clipped rather than wrapped — the screen is
 * a glance, the detail panel is for reading.
 */
export function drawScreen(screen, palette, lines) {
  if (!screen || !screen.ctx) return;
  const { ctx, canvas, texture } = screen;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = palette.screenBg;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.font = '600 15px ui-monospace, SFMono-Regular, Menlo, monospace';
  ctx.textBaseline = 'top';
  (lines || []).slice(0, 6).forEach((line, i) => {
    ctx.fillStyle = i === 0 ? palette.screenTextBright : palette.screenText;
    ctx.fillText(String(line == null ? '' : line).slice(0, 26), 10, 12 + i * 23);
  });
  texture.needsUpdate = true;
}

/* ---------- chair ---------- */

export function makeChair(palette) {
  const group = new THREE.Group();
  const seat = box(1.5, 0.2, 1.4, palette.chair);
  seat.position.y = 1.0;
  group.add(seat);
  const back = box(1.5, 1.2, 0.2, palette.chair);
  back.position.set(0, 1.6, 0.6);
  group.add(back);
  const post = cylinder(0.12, 0.12, 1.0, 8, palette.deskLeg);
  post.position.y = 0.5;
  group.add(post);
  const foot = cylinder(0.7, 0.75, 0.12, 10, palette.deskLeg);
  foot.position.y = 0.06;
  group.add(foot);
  return group;
}

/* ---------- person ---------- */

/**
 * A worker. Joints hang off named groups so `poseWorker` can drive them
 * without rebuilding anything.
 *
 * @returns {THREE.Group} `userData.joints` = {shoulderL, shoulderR, head, torso}
 */
export function makePerson(palette, tint) {
  const group = new THREE.Group();
  const shirt = material(tint || palette.shirt, { rough: 0.9 });
  const skin = material(palette.skin, { rough: 0.7 });

  const torso = new THREE.Group();
  torso.position.y = 1.55;
  group.add(torso);

  const chest = capsule(0.42, 0.8, shirt);
  chest.position.y = 0.4;
  torso.add(chest);

  const shoulderL = new THREE.Group();
  shoulderL.position.set(-0.5, 0.72, 0);
  const armL = capsule(0.15, 0.6, shirt);
  armL.position.y = -0.4;
  shoulderL.add(armL);
  torso.add(shoulderL);

  const shoulderR = new THREE.Group();
  shoulderR.position.set(0.5, 0.72, 0);
  const armR = capsule(0.15, 0.6, shirt);
  armR.position.y = -0.4;
  shoulderR.add(armR);
  torso.add(shoulderR);

  const head = new THREE.Group();
  head.position.y = 1.0;
  const skull = new THREE.Mesh(
    geometry('head', () => new THREE.SphereGeometry(0.45, 16, 14)), skin,
  );
  skull.castShadow = true;
  head.add(skull);
  const hair = new THREE.Mesh(
    geometry('hair', () => new THREE.SphereGeometry(
      0.47, 16, 10, 0, Math.PI * 2, 0, Math.PI * 0.55,
    )),
    material(palette.hair, { rough: 0.95 }),
  );
  hair.position.y = 0.05;
  head.add(hair);
  torso.add(head);

  group.userData.joints = { torso, shoulderL, shoulderR, head };
  group.userData.pose = 'work';
  group.userData.poseTargets = null;
  return group;
}

// Pose targets, in radians. The camera looks at the office from a fixed
// isometric angle and workers face inward, so these read as back-three-quarter
// silhouettes: arms forward onto the desk is the resting "working" shape.
const POSES = {
  work:    { shoulderX: -1.15, shoulderZ: 0.18, headX: 0.10, torsoX: 0.06, lift: 0 },
  tool:    { shoulderX: -1.45, shoulderZ: 0.30, headX: 0.16, torsoX: 0.16, lift: 0 },
  done:    { shoulderX: -0.20, shoulderZ: -0.30, headX: -0.10, torsoX: -0.12, lift: 0 },
  stopped: { shoulderX: -0.55, shoulderZ: 0.05, headX: 0.02, torsoX: 0.00, lift: 0 },
  error:   { shoulderX: -0.35, shoulderZ: 0.12, headX: 0.55, torsoX: 0.30, lift: -0.12 },
  idle:    { shoulderX: -0.45, shoulderZ: 0.00, headX: 0.00, torsoX: 0.00, lift: 0 },
};

export function poseTargets(pose) {
  return POSES[pose] || POSES.idle;
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

/**
 * Drive one worker toward its pose. Called every frame; `dt` is seconds since
 * the last frame, so the motion is frame-rate independent.
 *
 * `elapsed` seconds drives the small idle motion that keeps a working figure
 * from looking frozen — typing jitter while working, breathing otherwise.
 */
export function poseWorker(person, pose, elapsed, dt) {
  const joints = person && person.userData && person.userData.joints;
  if (!joints) return;
  const target = poseTargets(pose);
  // ~12Hz approach, capped so a long frame (tab restored) snaps rather than
  // overshoots past the target.
  const k = Math.min(1, dt * 12);

  const typing = pose === 'work' || pose === 'tool';
  const jitterL = typing ? Math.sin(elapsed * 9.0) * 0.07 : 0;
  const jitterR = typing ? Math.sin(elapsed * 7.4 + 1.3) * 0.08 : 0;
  const breathe = Math.sin(elapsed * 1.6) * 0.015;

  joints.shoulderL.rotation.x = lerp(joints.shoulderL.rotation.x, target.shoulderX + jitterL, k);
  joints.shoulderR.rotation.x = lerp(joints.shoulderR.rotation.x, target.shoulderX + jitterR, k);
  joints.shoulderL.rotation.z = lerp(joints.shoulderL.rotation.z, -target.shoulderZ, k);
  joints.shoulderR.rotation.z = lerp(joints.shoulderR.rotation.z, target.shoulderZ, k);
  joints.head.rotation.x = lerp(joints.head.rotation.x, target.headX, k);
  joints.torso.rotation.x = lerp(joints.torso.rotation.x, target.torsoX + breathe, k);
  joints.torso.position.y = lerp(joints.torso.position.y, 1.55 + target.lift, k);
  person.userData.pose = pose;
}

/* ---------- nameplate ---------- */

/**
 * A floating label above a desk. A sprite, so it always faces the camera and
 * stays readable at every zoom.
 *
 * @returns {THREE.Sprite} `userData.plate` = {canvas, ctx, texture}
 */
export function makeNameplate(palette, text) {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 96;
  const ctx = canvas.getContext('2d');
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: texture, transparent: true, depthWrite: false,
  }));
  sprite.scale.set(9.5, 1.8, 1);
  sprite.userData.plate = { canvas, ctx, texture };
  drawNameplate(sprite, palette, text, null);
  return sprite;
}

const STATUS_GLYPH = {
  running: '▶', completed: '✓', failed: '✕', error: '✕',
  timeout: '⏱', interrupted: '■',
  // Deliberately not '✓': the subagent stopped, but no completion was ever
  // reported, and a tick would claim a clean result we never saw.
  ended: '◦',
};

export function drawNameplate(sprite, palette, text, status) {
  const plate = sprite && sprite.userData && sprite.userData.plate;
  if (!plate) return;
  const { ctx, canvas, texture } = plate;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  ctx.fillStyle = palette.plateBg;
  // roundRect is recent enough (Safari 16.4) to be worth a fallback rather
  // than an exception that leaves every nameplate blank.
  if (typeof ctx.roundRect === 'function') {
    ctx.beginPath();
    ctx.roundRect(4, 18, canvas.width - 8, 60, 22);
    ctx.fill();
  } else {
    ctx.fillRect(4, 18, canvas.width - 8, 60);
  }

  const glyph = STATUS_GLYPH[status] || '';
  ctx.font = '600 30px ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif';
  ctx.textBaseline = 'middle';
  if (glyph) {
    ctx.fillStyle = palette.plateAccent;
    ctx.fillText(glyph, 22, 49);
  }
  ctx.fillStyle = palette.plateText;
  const label = String(text == null ? '' : text);
  ctx.fillText(label.length > 20 ? label.slice(0, 19) + '…' : label, glyph ? 60 : 22, 49);

  texture.needsUpdate = true;
}

/* ---------- disposal ---------- */

/**
 * Release the per-instance resources under `root` — the canvas textures and
 * the geometries/materials that belong to exactly one object. Shared cache
 * entries are left alone; `disposeSharedCaches` handles those when the whole
 * scene goes away.
 */
export function disposeTree(root) {
  if (!root) return;
  root.traverse(obj => {
    const screen = obj.userData && obj.userData.screen;
    if (screen) {
      screen.texture.dispose();
      screen.panelGeometry.dispose();
      screen.panelMaterial.dispose();
    }
    const plate = obj.userData && obj.userData.plate;
    if (plate) plate.texture.dispose();
    if (obj.isSprite && obj.material) obj.material.dispose();
  });
}

/** Drop the shared geometry/material caches. Only on full scene disposal. */
export function disposeSharedCaches() {
  _geometries.forEach(geo => { try { geo.dispose(); } catch (_err) { /* already gone */ } });
  _materials.forEach(mat => { try { mat.dispose(); } catch (_err) { /* already gone */ } });
  _geometries.clear();
  _materials.clear();
}
