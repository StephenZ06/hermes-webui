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
import { idlePoseFor } from './idle.js';

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

/**
 * A department name lying on the floor, letterspaced, as painted signage.
 *
 * Only the Business outlet has names worth painting — Projects pods are a
 * subagent's parent id, which means nothing to a reader. Passing no text
 * returns null rather than an empty sign.
 */
export function makeFloorTitle(text, width, palette, opts) {
  const label = String(text || '').trim();
  if (!label) return null;
  const fit = !!(opts && opts.fit);

  const canvas = document.createElement('canvas');
  canvas.width = 1024;
  canvas.height = fit ? 220 : 176;
  const ctx = canvas.getContext('2d');
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';

  const chars = Array.from(label.toUpperCase());
  let fontPx = 96;
  // Letterspacing by hand: ctx.letterSpacing is too new to rely on, and this
  // is the whole reason the sign reads as signage rather than a caption.
  let spacing = 16;

  if (fit) {
    // Pick the largest font (within bounds) whose letterspaced text spans ~92%
    // of the canvas, so a short name like "Sales" is painted as large as
    // "Operations" instead of a third the size. Tracking scales with the font.
    const trackRatio = 0.17;
    const widthAt = (px) => {
      ctx.font = `700 ${px}px Georgia, "Times New Roman", serif`;
      const sp = px * trackRatio;
      const w = chars.reduce((sum, c) => sum + ctx.measureText(c).width + sp, 0) - sp;
      return { w, sp };
    };
    const base = widthAt(100);
    fontPx = Math.max(84, Math.min(176, 100 * (canvas.width * 0.92) / base.w));
    spacing = widthAt(fontPx).sp;
  }

  ctx.font = `700 ${fontPx}px Georgia, "Times New Roman", serif`;
  const total = chars.reduce((sum, c) => sum + ctx.measureText(c).width + spacing, 0) - spacing;
  let x = (canvas.width - total) / 2;
  ctx.fillStyle = palette.floorTitle;
  for (const c of chars) {
    ctx.fillText(c, x, canvas.height / 2);
    x += ctx.measureText(c).width + spacing;
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  const height = width * (canvas.height / canvas.width);
  const geometry = new THREE.PlaneGeometry(width, height);
  const material = new THREE.MeshBasicMaterial({
    map: texture, transparent: true, opacity: 0.7, depthWrite: false,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.y = 0.66;
  // Tracked for disposal: this trio belongs to one pod, not to the caches.
  mesh.userData.floorTitle = { texture, geometry, material };
  return mesh;
}

/* ---------- progress outlines ---------- */

// How long an outline takes to come up or go quiet. Long enough to read as a
// current easing in rather than a line snapping on.
const DASH_FADE_MS = 800;

/**
 * A dashed line whose pattern can be marched along its own length.
 *
 * Built as a real THREE.Line with LineDashedMaterial rather than faked with
 * geometry, so the dashes stay crisp at every zoom. The base line distances
 * are kept because three's LineDashedMaterial has no dash offset of its own —
 * the movement has to come from rewriting that attribute.
 */
export function makeDashedLine(points, opts) {
  const options = opts || {};
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  const material = new THREE.LineDashedMaterial({
    color: options.color,
    dashSize: options.dashSize ?? 0.9,
    gapSize: options.gapSize ?? 0.7,
    transparent: true,
    opacity: options.opacity ?? 0.55,
  });
  const line = new THREE.Line(geometry, material);
  line.computeLineDistances();
  const attribute = geometry.getAttribute('lineDistance');
  line.userData.dashed = {
    geometry, material,
    base: Float32Array.from(attribute.array),
    // One dash plus one gap: shifting further repeats the pattern, so the
    // offset can wrap and never grow without bound.
    period: material.dashSize + material.gapSize,
    active: false,
    // Colour and opacity are eased between states rather than snapped, so a
    // platform coming to life reads as a current arriving.
    fade: null,
    idle: { color: new THREE.Color(options.color), opacity: options.opacity ?? 0.55 },
    live: { color: new THREE.Color(options.color), opacity: options.opacity ?? 0.55 },
  };
  return line;
}

/** The two appearances a dashed line eases between. */
export function setDashPalette(line, idleColor, idleOpacity, liveColor, liveOpacity) {
  const dashed = line && line.userData && line.userData.dashed;
  if (!dashed) return;
  dashed.idle.color.set(idleColor);
  dashed.idle.opacity = idleOpacity;
  dashed.live.color.set(liveColor);
  dashed.live.opacity = liveOpacity;
  const target = dashed.active ? dashed.live : dashed.idle;
  dashed.material.color.copy(target.color);
  dashed.material.opacity = target.opacity;
}

/** The outline tracing the edge of a platform. */
export function makeSlabOutline(width, depth, palette, height) {
  const hw = width / 2;
  const hd = depth / 2;
  const y = height == null ? 0.66 : height;
  // Five points rather than a LineLoop: computeLineDistances() only measures
  // the segments it is given, and a loop's closing edge would otherwise carry
  // no dash pattern at all.
  const line = makeDashedLine([
    new THREE.Vector3(-hw, y, -hd),
    new THREE.Vector3(hw, y, -hd),
    new THREE.Vector3(hw, y, hd),
    new THREE.Vector3(-hw, y, hd),
    new THREE.Vector3(-hw, y, -hd),
  ], { color: palette.outlineIdle, dashSize: 0.9, gapSize: 0.7, opacity: 0.6 });
  setDashPalette(line, palette.outlineIdle, 0.6, palette.outlineActive, 0.95);
  return line;
}

/**
 * The line joining the conductor to one pod.
 *
 * Dashed and marching like the platform outlines: the charge travels out from
 * the conductor toward the pod, which is what makes the bridge read as
 * carrying something rather than merely existing. Finer dashes than a
 * platform edge so the two are still distinguishable where they meet.
 */
export function makeConnector(fromX, fromZ, toX, toZ, palette, height) {
  const y = height == null ? 0.34 : height;
  const line = makeDashedLine([
    new THREE.Vector3(fromX, y, fromZ),
    new THREE.Vector3(toX, y, toZ),
  ], { color: palette.connector, dashSize: 0.55, gapSize: 0.85, opacity: 0.45 });
  // Idle opacity 0: an unlit bridge is not drawn at all, so a delegation
  // starting reads as the charge *arriving* — the line fades up from nothing
  // over DASH_FADE_MS rather than a green dash-line appearing at full strength.
  setDashPalette(line, palette.connector, 0.0, palette.outlineActive, 0.9);
  return line;
}

/**
 * Shift a dashed line's pattern along its own length.
 * @param {THREE.Line} line from `makeDashedLine`
 * @param {number} offset distance travelled, in world units
 */
export function marchOutline(line, offset) {
  const dashed = line && line.userData && line.userData.dashed;
  if (!dashed) return;
  const attribute = dashed.geometry.getAttribute('lineDistance');
  const shift = offset % dashed.period;
  for (let i = 0; i < dashed.base.length; i += 1) {
    attribute.array[i] = dashed.base[i] + shift;
  }
  attribute.needsUpdate = true;
}

/**
 * Switch a dashed line between its live and idle appearance.
 *
 * Starts an eased transition rather than assigning outright: a line that snaps
 * from grey to green the instant a subagent spawns reads as a glitch, where
 * the same change over ~400ms reads as a current arriving.
 */
export function setOutlineActive(line, active) {
  const dashed = line && line.userData && line.userData.dashed;
  if (!dashed || dashed.active === active) return;
  dashed.active = active;
  const target = active ? dashed.live : dashed.idle;
  dashed.fade = {
    elapsed: 0,
    duration: DASH_FADE_MS,
    fromColor: dashed.material.color.clone(),
    fromOpacity: dashed.material.opacity,
    toColor: target.color.clone(),
    toOpacity: target.opacity,
  };
}

// Ease-out: the change is quickest at the start, which is what makes it feel
// like something switching on rather than sliding.
function easeOutCubic(t) {
  return 1 - Math.pow(1 - t, 3);
}

/**
 * Advance a dashed line's appearance transition.
 * @param {number} dtMs milliseconds since the last frame
 * @returns {boolean} true while still animating
 */
export function advanceDashFade(line, dtMs) {
  const dashed = line && line.userData && line.userData.dashed;
  if (!dashed || !dashed.fade) return false;
  const fade = dashed.fade;
  fade.elapsed += dtMs;
  const t = Math.min(1, fade.elapsed / fade.duration);
  const k = easeOutCubic(t);
  dashed.material.color.copy(fade.fromColor).lerp(fade.toColor, k);
  dashed.material.opacity = fade.fromOpacity + (fade.toOpacity - fade.fromOpacity) * k;
  if (t >= 1) {
    dashed.fade = null;
    return false;
  }
  return true;
}

/** True when this line is currently showing its live appearance. */
export function isDashActive(line) {
  const dashed = line && line.userData && line.userData.dashed;
  return !!(dashed && dashed.active);
}

/* ---------- set dressing ---------- */

/**
 * A potted plant. Purely scenery — it carries no state and never changes, so
 * it can never mislead anyone about what Hermes is doing.
 */
export function makePlant(palette) {
  const group = new THREE.Group();
  const pot = cylinder(0.42, 0.34, 0.7, 10, palette.pot);
  pot.position.y = 0.35;
  group.add(pot);
  // Three offset blades rather than a sphere: reads as foliage at this scale.
  for (let i = 0; i < 3; i += 1) {
    const blade = new THREE.Mesh(
      geometry(`blade|${i}`, () => new THREE.ConeGeometry(0.42, 1.5, 6)),
      material(palette.plant, { rough: 0.95 }),
    );
    blade.position.set(Math.cos(i * 2.1) * 0.18, 1.35, Math.sin(i * 2.1) * 0.18);
    blade.rotation.z = Math.cos(i * 2.1) * 0.22;
    blade.rotation.x = Math.sin(i * 2.1) * 0.22;
    blade.castShadow = true;
    group.add(blade);
  }
  return group;
}

/**
 * A walkway slab joining a pod back toward the conductor, so the floor plan
 * reads as a place with circulation rather than islands in a void.
 */
export function makeWalkway(length, palette) {
  const slab = box(2.6, 0.06, Math.max(1, length), palette.walkway);
  slab.position.y = 0.04;
  slab.castShadow = false;
  slab.receiveShadow = true;
  return slab;
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

  // Legs exist only so a figure can walk. Seated at a desk they are behind
  // furniture and hidden, which is why the office got this far without them.
  const legs = new THREE.Group();
  const hipL = new THREE.Group();
  hipL.position.set(-0.19, 0, 0);
  const legL = capsule(0.155, 0.62, material(palette.trousers, { rough: 0.95 }));
  legL.position.y = -0.42;
  hipL.add(legL);
  const hipR = new THREE.Group();
  hipR.position.set(0.19, 0, 0);
  const legR = capsule(0.155, 0.62, material(palette.trousers, { rough: 0.95 }));
  legR.position.y = -0.42;
  hipR.add(legR);
  legs.add(hipL, hipR);
  legs.position.y = 1.55;
  legs.visible = false;
  group.add(legs);

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

  group.userData.joints = { torso, shoulderL, shoulderR, head, legs, hipL, hipR };
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

  // ---- idle behaviours -------------------------------------------------
  // Decoration, not state. These only ever play over `work` — a figure that
  // is thinking rather than mid-tool-call — and each one is visually distinct
  // from every pose above that *means* something, so nobody reads a stretch
  // as an error or a sip as a completion.
  //
  // `lean` and `sip` keep the figure at the desk; `stretch` stands it up.
  lean:    { shoulderX: -0.55, shoulderZ: -0.22, headX: 0.20, torsoX: -0.16, lift: 0 },
  sip:     { shoulderX: -1.70, shoulderZ: 0.55, headX: -0.14, torsoX: 0.02, lift: 0 },
  stretch: { shoulderX: -2.55, shoulderZ: -0.70, headX: -0.18, torsoX: -0.06, lift: 0.35 },
  glance:  { shoulderX: -1.05, shoulderZ: 0.16, headX: 0.05, torsoX: 0.04, lift: 0, headY: 0.85 },
};

/**
 * Drive a figure that is on its feet.
 *
 * Separate from poseWorker's eased targets because walking is periodic rather
 * than a state to settle into: the limbs swing off a phase, and the whole
 * figure bobs with the stride.
 *
 * @param {THREE.Group} person from `makePerson`
 * @param {number} phase distance walked, in world units
 * @param {number} settle 0..1 — how much of the walk to apply, so a figure can
 *   ease out of it as it arrives rather than stopping mid-stride
 */
export function poseWalking(person, phase, settle) {
  const joints = person && person.userData && person.userData.joints;
  if (!joints) return;
  const k = settle == null ? 1 : Math.max(0, Math.min(1, settle));
  const swing = Math.sin(phase * 2.6) * 0.62 * k;
  joints.legs.visible = k > 0.02;
  joints.hipL.rotation.x = swing;
  joints.hipR.rotation.x = -swing;
  // Arms counter-swing, and the torso rides the stride.
  joints.shoulderL.rotation.x = -swing * 0.55;
  joints.shoulderR.rotation.x = swing * 0.55;
  joints.shoulderL.rotation.z = 0;
  joints.shoulderR.rotation.z = 0;
  joints.head.rotation.x = 0.05 * k;
  joints.head.rotation.y = 0;
  joints.torso.rotation.x = 0.09 * k;
  joints.torso.position.y = 1.55 + Math.abs(Math.sin(phase * 2.6)) * 0.06 * k;
}

/** Put the legs away — a seated figure has none as far as the office knows. */
export function hideLegs(person) {
  const joints = person && person.userData && person.userData.joints;
  if (joints && joints.legs) joints.legs.visible = false;
}

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
  // Anything driven by poseWorker is at a desk; only poseWalking shows legs.
  if (joints.legs) joints.legs.visible = false;
  // An idle behaviour may be playing over plain work; everything below drives
  // toward whichever pose that resolves to.
  const played = idlePoseFor(person.userData, pose, elapsed * 1000);
  const target = poseTargets(played);
  // ~12Hz approach, capped so a long frame (tab restored) snaps rather than
  // overshoots past the target.
  const k = Math.min(1, dt * 12);

  const typing = played === 'work' || played === 'tool';
  const jitterL = typing ? Math.sin(elapsed * 9.0) * 0.07 : 0;
  const jitterR = typing ? Math.sin(elapsed * 7.4 + 1.3) * 0.08 : 0;
  const breathe = Math.sin(elapsed * 1.6) * 0.015;

  joints.shoulderL.rotation.x = lerp(joints.shoulderL.rotation.x, target.shoulderX + jitterL, k);
  joints.shoulderR.rotation.x = lerp(joints.shoulderR.rotation.x, target.shoulderX + jitterR, k);
  joints.shoulderL.rotation.z = lerp(joints.shoulderL.rotation.z, -target.shoulderZ, k);
  joints.shoulderR.rotation.z = lerp(joints.shoulderR.rotation.z, target.shoulderZ, k);
  joints.head.rotation.x = lerp(joints.head.rotation.x, target.headX, k);
  // A glance turns the head toward a neighbour; every other pose faces front.
  const headY = target.headY ? (person.userData.glanceDir || target.headY) : 0;
  joints.head.rotation.y = lerp(joints.head.rotation.y, headY, k);
  joints.torso.rotation.x = lerp(joints.torso.rotation.x, target.torsoX + breathe, k);
  joints.torso.position.y = lerp(joints.torso.position.y, 1.55 + target.lift, k);
  person.userData.pose = played;
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
  canvas.width = 640;
  canvas.height = 96;
  const ctx = canvas.getContext('2d');
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: texture, transparent: true, depthWrite: false,
  }));
  // A little wider than the old 9.5, and the canvas is bigger and the text now
  // measure-fits to the edge — the old plate clipped at ~20 characters with the
  // box half empty to the right.
  sprite.scale.set(11, 1.7, 1);
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

/** Clip `text` to `maxWidth` px under the context's current font, with an ellipsis. */
function fitText(ctx, text, maxWidth) {
  if (ctx.measureText(text).width <= maxWidth) return text;
  let lo = 0;
  let hi = text.length;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (ctx.measureText(text.slice(0, mid) + '…').width <= maxWidth) lo = mid;
    else hi = mid - 1;
  }
  return text.slice(0, lo).trimEnd() + '…';
}

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
  const textX = glyph ? 60 : 22;
  // Fill the plate to its edge, then ellipsize — a fixed character cap left the
  // box visibly half-used.
  const room = canvas.width - textX - 18;
  const label = String(text == null ? '' : text);
  ctx.fillText(fitText(ctx, label, room), textX, 49);

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
    const dashed = obj.userData && obj.userData.dashed;
    if (dashed) {
      dashed.geometry.dispose();
      dashed.material.dispose();
    }
    const title = obj.userData && obj.userData.floorTitle;
    if (title) {
      title.texture.dispose();
      title.geometry.dispose();
      title.material.dispose();
    }
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
