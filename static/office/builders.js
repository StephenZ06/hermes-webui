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

// Every bridge, including the Floor's pitched route, uses this footprint.
// Keeping it in the shared builder prevents perspective tweaks from quietly
// producing a different-width structural deck for one destination.
export const BRIDGE_DECK_WIDTH = 3.6;
const BRIDGE_DECK_HEIGHT = 0.34;

/** Shared material, keyed by colour and finish. */
export function material(color, opts) {
  const options = opts || {};
  const physical = options.physical ? 1 : 0;
  const unlit = options.unlit ? 1 : 0;
  const clearcoat = options.clearcoat ?? 0;
  const key = `${color}|${options.rough ?? 0.85}|${options.metal ?? 0.02}|${options.emissive || ''}|${options.ei ?? 0}|${physical}|${unlit}|${clearcoat}|${options.transparent ?? false}`;
  let mat = _materials.get(key);
  if (!mat) {
    const params = { color };
    // MeshBasicMaterial is intentionally unlit and does not support the
    // PBR-only roughness/metalness fields. Supplying them produces a Three.js
    // console warning on every Office load.
    if (!unlit) {
      params.roughness = options.rough ?? 0.85;
      params.metalness = options.metal ?? 0.02;
    }
    if (options.emissive) {
      params.emissive = options.emissive;
      params.emissiveIntensity = options.ei ?? 1;
    }
    if (options.transparent) {
      params.transparent = true;
      params.opacity = options.opacity ?? 0.5;
    }
    if (unlit) {
      mat = new THREE.MeshBasicMaterial(params);
    } else if (physical) {
      params.clearcoat = clearcoat;
      params.clearcoatRoughness = options.clearcoatRough ?? 0.15;
      mat = new THREE.MeshPhysicalMaterial(params);
    } else {
      mat = new THREE.MeshStandardMaterial(params);
    }
    _materials.set(key, mat);
  }
  return mat;
}

/** A 2D rounded rectangle shape, extrudable into a platform with soft edges. */
function roundedRectShape(width, depth, radius) {
  const w = width / 2;
  const d = depth / 2;
  const r = Math.min(radius, w - 0.05, d - 0.05);
  const shape = new THREE.Shape();
  shape.moveTo(-w + r, -d);
  shape.lineTo(w - r, -d);
  shape.absarc(w - r, -d + r, r, -Math.PI / 2, 0, false);
  shape.lineTo(w, d - r);
  shape.absarc(w - r, d - r, r, 0, Math.PI / 2, false);
  shape.lineTo(-w + r, d);
  shape.absarc(-w + r, d - r, r, Math.PI / 2, Math.PI, false);
  shape.lineTo(-w, -d + r);
  shape.absarc(-w + r, -d + r, r, Math.PI, Math.PI * 1.5, false);
  return shape;
}

/** A rounded platform mesh with a dark, slightly glossy base and a rim. */
function roundedPlatform(width, depth, height, color, opts) {
  const options = opts || {};
  const radius = options.radius ?? Math.min(width, depth) * 0.12;
  // ExtrudeGeometry's bevel extends beyond both ends of its nominal depth.
  // Reserve that space inside the requested height so `height` remains the
  // rendered thickness callers lay out against.
  const bevel = options.bevel ?? 0.15;
  const enableBevel = bevel > 0.001;
  const clampedBevel = enableBevel ? Math.min(bevel, Math.max(0.001, height / 2 - 0.001)) : 0;
  const coreHeight = enableBevel ? Math.max(0.001, height - clampedBevel * 2) : height;
  const shape = roundedRectShape(width, depth, radius);
  const geo = geometry(
    `rounded-platform|${width}|${depth}|${height}|${radius}|${bevel}|${enableBevel ? 1 : 0}`,
    () => new THREE.ExtrudeGeometry(shape, {
      depth: coreHeight,
      bevelEnabled: enableBevel,
      bevelThickness: clampedBevel,
      bevelSize: clampedBevel,
      bevelSegments: options.bevelSegments ?? 3,
      steps: 1,
    }),
  );
  // ExtrudeGeometry extrudes along +z from the XY shape. Centre the slab in
  // that extrusion direction so the mesh's origin sits at its geometric centre;
  // the caller rotates the mesh to stand it upright. Mutating a shared cached
  // geometry would rotate every platform that reuses it, so all orientation is
  // kept on the mesh.
  geo.computeBoundingBox();
  const bounds = geo.boundingBox;
  if (bounds) geo.translate(0, 0, -(bounds.min.z + bounds.max.z) / 2);
  const mat = options.material || material(color, options.matOpts);
  const mesh = new THREE.Mesh(geo, mat);
  // Stand the slab up so the extrusion axis becomes +y; the top face (+z end)
  // becomes the upper deck at +y.
  mesh.rotation.x = -Math.PI / 2;
  mesh.castShadow = options.castShadow !== false;
  mesh.receiveShadow = options.receiveShadow !== false;
  return mesh;
}

/**
 * A straight bridge deck with square terminal faces. Platform slabs remain
 * rounded, but bridge terminals must reach the whole way across their rim;
 * rounded caps leave a visible notch at that connection in the isometric view.
 */
function makeRectangularBridgeDeck(width, depth, height, color, opts) {
  const options = opts || {};
  const geo = geometry(
    `rectangular-bridge|${width}|${depth}|${height}`,
    () => new THREE.BoxGeometry(width, height, depth),
  );
  const mesh = new THREE.Mesh(geo, options.material || material(color, options.matOpts));
  mesh.castShadow = options.castShadow !== false;
  mesh.receiveShadow = options.receiveShadow !== false;
  return mesh;
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

/**
 * A box with softly rounded edges, lying flat (w across x, h up y, d along z).
 * Furniture built from plain boxes read as blocky next to the rounded pod
 * slabs; this reuses the same extrusion.
 */
function roundedSlab(w, h, d, color, radius) {
  const r = radius ?? Math.min(w, d) * 0.08;
  return roundedPlatform(w, d, h, color, { radius: r, bevel: Math.min(r, h * 0.45), bevelSegments: 2 });
}

/** The same, standing upright (w across x, h up y, t thick along z). */
function roundedPanel(w, h, t, color, radius) {
  const r = radius ?? Math.min(w, h) * 0.08;
  const mesh = roundedPlatform(w, h, t, color, { radius: r, bevel: Math.min(r, t * 0.45), bevelSegments: 2 });
  mesh.rotation.x = 0;
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
    geometry(`cap|${radius}|${length}`, () => new THREE.CapsuleGeometry(radius, length, 4, 12)),
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
/**
 * `tint`, when given (a department's accent colour — see roster.js's
 * colorForDepartment — or a Projects cluster's derived one, see layout.js's
 * colorForProjectsCluster), is blended into the palette's own pod colours
 * rather than replacing them: a floor reads as its department/cluster while
 * staying the same material and staying correct in both the light and dark
 * palette, instead of a flat brand colour painted over whichever theme is
 * active. The blend is weighted heavily toward the tint (0.62/0.68) so a
 * coloured floor actually reads as coloured at a glance rather than a faint
 * wash over the neutral palette.
 */
/**
 * A raised pod plinth.
 */
export function makePod(width, depth, palette, tint) {
  const group = new THREE.Group();
  const topColor = tint ? mixColor(palette.podTop, tint, 0.62) : palette.podTop;
  const isUntinted = !tint;
  // Keep the bases unmistakably dark while retaining enough contrast against
  // the near-black office floor to make both black tiers visible.
  const baseColor = '#242b3b';
  const radius = Math.min(width, depth) * 0.12;

  function addLayer(name, height, color, y, options) {
    const layerOptions = options || {};
    const layer = roundedPlatform(
      layerOptions.layerWidth ?? width,
      layerOptions.layerDepth ?? depth,
      height,
      color,
      Object.assign({
      // The rounded 2D silhouette remains, but the stacked faces themselves
      // need virtually no bevel: a bevel at every shared edge makes the
      // bands recess into shadow instead of reading as one flush platform.
      radius, bevel: 0.001, bevelSegments: 1,
      }, layerOptions),
    );
    layer.position.y = y;
      // Keep every layer centered on the same footprint. The alternating
      // widths/depths create the visible ledges without a diagonal shift.
    layer.position.x = 0;
      layer.position.z = 0;
    layer.userData.platformLayer = name;
    group.add(layer);
    return layer;
  }

  // Four flush layers make the pod read as one substantial platform: coloured
  // floor, black base, the delivery-coloured layer, then its black footing.
  // The upper surface stays at y=0.6, preserving the existing desk, label,
  // and bridge elevations.
  const baseHeight = 1.2;
  const layerHeight = baseHeight;
  // At overview zoom a tiny footprint change is sub-pixel after isometric
  // projection. This step is large enough to reveal each equal-height tier,
  // while remaining a single compact stacked platform rather than terraces.
  const step = 4;
  // Untinted platforms (Conductor, The Floor) are dark and near-black; any
  // glossy rim highlight reads as a white artifact against them. Give them a
  // matte, low-metal finish while tinted department floors keep a subtle
  // satin clearcoat.
  const topMatOpts = isUntinted
    ? { physical: true, metal: 0.04, rough: 0.92, clearcoat: 0 }
    : { physical: true, metal: 0.06, rough: 0.8, clearcoat: 0 };
  const slab = addLayer('top', layerHeight, topColor, 0, { matOpts: topMatOpts });
  slab.castShadow = true;
  addLayer('upper-base', layerHeight, baseColor, -1.2, {
    layerWidth: width + step * 2,
    layerDepth: depth + step * 2,
    matOpts: { rough: 0.92, metal: 0.04 },
  });

  // Unlike the shared top material, this lower coloured slab owns its own
  // emissive material so a delivery can bloom at one destination only.
  const deliveryMaterial = material(topColor, topMatOpts).clone();
  // Un-tinted platforms (The Floor and Conductor) should not create a white
  // specular pinprick at their rim. Their delivery tier still participates in
  // the activity pulse, but starts dark until a real arrival wave reaches it.
  const deliveryIdleIntensity = tint ? 2.0 : 0;
  deliveryMaterial.emissive.set(tint || topColor).multiplyScalar(2.2);
  deliveryMaterial.emissiveIntensity = deliveryIdleIntensity;
  const delivery = addLayer('delivery', layerHeight, topColor, -2.4, {
    layerWidth: width + step * 2,
    layerDepth: depth + step * 2,
    material: deliveryMaterial,
  });
  delivery.userData.idleEmissiveIntensity = deliveryIdleIntensity;
  addLayer('lower-base', layerHeight, baseColor, -3.6, {
    // The lowest footing must be at least as wide as the coloured delivery
    // tier above it, otherwise a dark gap/shadow shows along the bottom rim.
    layerWidth: width + step * 2,
    layerDepth: depth + step * 2,
    matOpts: { rough: 0.92, metal: 0.04 },
  });
  group.userData.deliveryLayer = delivery;
  return group;
}

/** THREE.Color.lerp under a hex-in, hex-out signature so callers (and the
 * material cache, which keys on the exact colour string) never touch a
 * THREE.Color instance directly. */
function mixColor(baseHex, tintHex, amount) {
  return '#' + new THREE.Color(baseHex).lerp(new THREE.Color(tintHex), amount).getHexString();
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

  // Filled in the palette's own signage tone, with a contrasting stroke
  // behind it: the floor under the sign is now a saturated department/
  // cluster colour rather than a plain palette tone, and a fixed light-grey
  // fill alone reads fine on some floor colours and vanishes on others. The
  // stroke is what keeps the letters legible whatever they sit on.
  ctx.lineJoin = 'round';
  ctx.lineWidth = Math.max(3, fontPx * 0.08);
  ctx.strokeStyle = palette.floorTitleStroke;
  ctx.fillStyle = palette.floorTitle;
  for (const c of chars) {
    ctx.strokeText(c, x, canvas.height / 2);
    ctx.fillText(c, x, canvas.height / 2);
    x += ctx.measureText(c).width + spacing;
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  const height = width * (canvas.height / canvas.width);
  const geometry = new THREE.PlaneGeometry(width, height);
  const material = new THREE.MeshBasicMaterial({
    map: texture, transparent: true, opacity: 0.85, depthWrite: false,
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
  // Just proud of the slab top (0.6): the isometric camera looks down at an
  // angle, so a point held higher above the slab at the same x/z projects to
  // a screen position shifted outward from the slab's own edge -- the higher
  // the gap, the more the dashes visibly "stick out" past the floor's own
  // corners. 0.66 (this used to match the floor sign's height) made that
  // gap noticeable; this sits right at the surface instead.
  const y = height == null ? 0.605 : height;
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
  // The pod and standard bridge decks finish at y=0.6. Keep the animated
  // current just above that shared surface so depth rendering cannot hide it.
  const y = height == null ? 0.66 : height;
  return makeConnector3d(
    { x: fromX, y, z: fromZ },
    { x: toX, y, z: toZ },
    palette,
  );
}

/** A dashed current trace between two fully three-dimensional endpoints. */
export function makeConnector3d(from, to, palette) {
  const line = makeDashedLine([
    new THREE.Vector3(from.x, from.y, from.z),
    new THREE.Vector3(to.x, to.y, to.z),
  ], { color: palette.connector, dashSize: 0.48, gapSize: 0.56, opacity: 0.45 });
  // Idle opacity 0: an unlit bridge is not drawn at all, so a delegation
  // starting reads as the charge *arriving* — the line fades up from nothing
  // over DASH_FADE_MS rather than a green dash-line appearing at full strength.
  setDashPalette(line, palette.connector, 0.0, palette.outlineActive, 1.0);
  // WebGL line widths are fixed by most browsers; draw this current after the
  // deck instead so its electrical movement stays readable at overview zoom.
  line.renderOrder = 4;
  return line;
}

/**
 * One active-current line per physical deck segment. Each sits just above its
 * own surface, so the charge follows a ramp instead of cutting across it.
 */
export function makeRouteConnector(segments, palette, clearance = 0.025) {
  const group = new THREE.Group();
  const dashedLines = (Array.isArray(segments) ? segments : []).map(segment => {
    const line = makeConnector3d(
      { x: segment.from.x, y: segment.fromTopY + clearance, z: segment.from.z },
      { x: segment.to.x, y: segment.toTopY + clearance, z: segment.to.z },
      palette,
    );
    group.add(line);
    return line;
  });
  group.userData.dashedLines = dashedLines;
  return group;
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
export function easeOutCubic(t) {
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
 * A soft coloured wash over a pod's floor, shown only while the pod is doing
 * real work (see scene.js's `record.active`). Its own per-instance material
 * (never the shared `material()` cache — every pod's activity state is
 * independent, and two different clusters can share a colour, see layout.js's
 * `colorForProjectsCluster`) so its opacity can pulse without touching any
 * other pod. The colour is pushed past normal 0-1 range on purpose: with the
 * scene's bloom pass in place (see scene.js), only pixels brighter than that
 * range actually bloom, which is what makes a working pod visibly glow
 * instead of just tinting a bit brighter.
 */
export function makePodGlow(width, depth, tint) {
  // The previous oversized plane bloomed as a bright rectangle beyond the
  // slab. Use the same rounded footprint, inset within the platform itself.
  const inset = 0.36;
  const glowWidth = Math.max(0.2, width - inset);
  const glowDepth = Math.max(0.2, depth - inset);
  const geometry = new THREE.ShapeGeometry(
    roundedRectShape(glowWidth, glowDepth, Math.min(glowWidth, glowDepth) * 0.12),
  );
  const color = new THREE.Color(tint || '#ffffff');
  color.multiplyScalar(2.4);
  const material = new THREE.MeshBasicMaterial({
    color, transparent: true, opacity: 0, depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.y = 0.61;
  mesh.userData.podGlow = { geometry, material };
  return mesh;
}

/**
 * A small whiteboard on a stand — one extra piece of set dressing per pod
 * alongside the two plants, purely for visual variety. Carries no state.
 *
 * Never casts a shadow: a decorative prop this small isn't worth the shadow
 * pass rendering four more objects from the light's point of view on every
 * pod, every frame -- the same reasoning makeWalkway and makeFloorTitle
 * already apply to their own meshes.
 */
export function makeWhiteboard(palette) {
  const group = new THREE.Group();
  const board = box(1.7, 1.15, 0.06, palette.board);
  board.position.y = 1.35;
  board.castShadow = false;
  group.add(board);
  const frame = box(1.8, 1.25, 0.05, palette.deskLeg);
  frame.position.set(0, 1.35, -0.02);
  frame.castShadow = false;
  group.add(frame);
  [-0.7, 0.7].forEach(sx => {
    const leg = cylinder(0.04, 0.04, 1.35, 6, palette.deskLeg);
    leg.position.set(sx, 0.675, 0);
    leg.castShadow = false;
    group.add(leg);
  });
  return group;
}

/**
 * A walkway slab joining a pod back toward the conductor, so the floor plan
 * reads as a place with circulation rather than islands in a void.
 *
 * Options:
 *   railColor: destination accent colour for the glowing side rails
 *   segmentColor: tint for the bridge body (defaults to palette.bridgeDeck)
 *   beamColor: underside tint (defaults to palette.bridgeBeam)
 */
export function makeBridgeActivityChevrons(length, deckHeight, activeColor, panelDividers) {
  const group = new THREE.Group();
  const shape = new THREE.Shape();
  // Filled triangular markers stay unmistakable at overview zoom.
  shape.moveTo(-0.48, -0.36); shape.lineTo(0.48, -0.36); shape.lineTo(0, 0.48); shape.closePath();
  const geometry = new THREE.ShapeGeometry(shape);
  const chevrons = [];
  // The visible divider lines are the rectangle boundaries. Put each marker
  // at the midpoint of adjacent boundaries so it never lands on a line.
  const dividers = Array.isArray(panelDividers) ? panelDividers : [];
  const boundaries = [-length / 2, ...dividers, length / 2];
  for (let i = 0; i < boundaries.length - 1; i += 1) {
    // This material is animated per marker. Clone the cached base material so
    // one inactive bridge cannot overwrite an active bridge's glow each frame.
    const chevronMat = material('#334155', { emissive: '#0b1220', ei: 0.1, transparent: true, opacity: 0.72 }).clone();
    // Flat markers may be seen from either side of a pitched Floor route.
    // Double-sided rendering keeps the destination-facing arrow readable.
    chevronMat.side = THREE.DoubleSide;
    const chevron = new THREE.Mesh(geometry, chevronMat);
    // Local +Z is conductor → platform, so rotate the arrow to face +Z.
    chevron.rotation.x = Math.PI / 2;
    chevron.position.set(0, deckHeight / 2 + 0.07, (boundaries[i] + boundaries[i + 1]) / 2);
    chevron.renderOrder = 6;
    chevron.userData.activeColor = activeColor || '#7dd3fc';
    group.add(chevron); chevrons.push(chevron);
  }
  group.userData.activityChevrons = chevrons;
  return group;
}

export function makeBridgeSegment(length, palette, options) {
  const opts = options || {};
  const dimensions = {
    width: BRIDGE_DECK_WIDTH,
    height: BRIDGE_DECK_HEIGHT,
    depth: Math.max(1, length),
  };
  const group = new THREE.Group();

  // Main graphite deck, slightly glossy but dark.
  const deckColor = opts.segmentColor || palette.bridgeDeck || palette.walkway;
  const deck = makeRectangularBridgeDeck(
    dimensions.width, dimensions.depth, dimensions.height, deckColor,
    {
      matOpts: { physical: true, metal: 0.18, rough: 0.55, clearcoat: 0.35 },
    },
  );
  deck.position.y = 0;
  deck.castShadow = false;
  deck.receiveShadow = true;
  group.add(deck);

  // Recessed structural beam giving the bridge visible depth from below.
  const beamColor = opts.beamColor || palette.bridgeBeam || palette.platformBase || '#3a3a42';
  const beam = makeRectangularBridgeDeck(
    dimensions.width - 0.48, dimensions.depth, 0.26,
    beamColor,
    { matOpts: { metal: 0.25, rough: 0.6 } },
  );
  beam.position.y = -0.29;
  beam.castShadow = false;
  group.add(beam);

  // Evenly spaced low-contrast panel divisions across the deck surface.
  // These read as structure rather than decoration; they stay dark so the
  // bridge looks premium, not busy.
  const panelSpacing = 2.0;
  const panelCount = Math.max(2, Math.floor(length / panelSpacing));
  const panelWidth = 0.08;
  const panelDepth = dimensions.width - 0.35;
  const panelColor = shadeColor(deckColor, -0.12);
  const panelMat = material(panelColor, { metal: 0.1, rough: 0.7 });
  const panelDividers = [];
  // Start at the first interior divider to complete the conductor-side deck
  // rectangle, while keeping the far platform-edge divider clear.
  for (let i = 1; i < panelCount - 1; i++) {
    const t = (i + 0.5) / panelCount;
    const panel = new THREE.Mesh(
      geometry(`bridge-panel|${panelDepth}|${panelWidth}`, () => new THREE.BoxGeometry(panelDepth, 0.04, panelWidth)),
      panelMat,
    );
    const z = (t - 0.5) * dimensions.depth;
    panel.position.set(0, dimensions.height / 2 + 0.015, z);
    panelDividers.push(z);
    panel.userData.bridgePanel = true;
    panel.castShadow = false;
    panel.receiveShadow = true;
    group.add(panel);
  }

  // Two physical cables span the full deck from platform edge to platform
  // edge. Their animated current is toggled by scene activity state, never by
  // the destination-coloured side rails.
  group.add(makeBridgeActivityChevrons(dimensions.depth, dimensions.height, opts.railColor, panelDividers));

  // Glowing side rails along the outer edges only. The rail colour matches
  // the destination platform; the emissive material lets them bloom gently.
  const railColor = opts.railColor;
  if (railColor) {
    // The structural deck may run beneath a platform rim to remove any
    // visible gap. Keep the illuminated rails on the exposed bridge instead
    // of letting their taller profile appear to bleed across that platform.
    const railTrimStart = Math.max(0, opts.railTrimStart || 0);
    const railTrimEnd = Math.max(0, opts.railTrimEnd || 0);
    const railSize = {
      width: 0.18,
      height: 0.22,
      depth: Math.max(0.1, dimensions.depth - railTrimStart - railTrimEnd),
    };
    const railMat = material(railColor, {
      emissive: railColor, ei: 1.8, metal: 0.1, rough: 0.35,
      transparent: true, opacity: 0.55,
    });
    const railLeft = new THREE.Mesh(
      geometry(`bridge-rail|${railSize.width}|${railSize.height}|${railSize.depth}`,
        () => new THREE.BoxGeometry(railSize.width, railSize.height, railSize.depth)),
      railMat,
    );
    railLeft.position.set(
      -dimensions.width / 2 + railSize.width / 2,
      dimensions.height / 2 + railSize.height / 2 - 0.02,
      (railTrimStart - railTrimEnd) / 2,
    );
    railLeft.castShadow = false;
    group.add(railLeft);

    const railRight = railLeft.clone();
    railRight.position.x = dimensions.width / 2 - railSize.width / 2;
    group.add(railRight);

    // Store material references so the scene can pulse rail brightness when
    // the destination pod is active.
    group.userData.railMaterials = [railMat];
  }

  return group;
}

/** Lighten or darken a hex colour by a fraction (-1..1). Returns hex. */
function shadeColor(hex, fraction) {
  const c = new THREE.Color(hex);
  const hsl = {};
  c.getHSL(hsl);
  hsl.l = Math.max(0, Math.min(1, hsl.l + fraction));
  c.setHSL(hsl.h, hsl.s, hsl.l);
  return '#' + c.getHexString();
}

export function makeWalkway(length, palette, railColor, options) {
  const bridgeOptions = Object.assign({}, options || {});
  if (railColor) bridgeOptions.railColor = railColor;
  const group = makeBridgeSegment(length, palette, bridgeOptions);
  // Department walkways sit just below the platform top. Their ends extend
  // beneath the rim, making a clean physical connection without drawing over
  // a platform's visible surface.
  group.children.forEach(part => { part.position.y += 0.63; });
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

  const top = roundedSlab(4.4, 0.2, 2.4, palette.deskTop, 0.14);
  top.position.y = 1.5;
  group.add(top);

  [-1.9, 1.9].forEach(x => {
    const leg = roundedSlab(0.25, 1.5, 2.0, palette.deskLeg, 0.06);
    leg.position.set(x, 0.75, 0);
    group.add(leg);
  });

  const screen = makeScreen(palette);
  screen.position.set(0, 2.5, -0.7);
  group.add(screen);
  group.userData.screen = screen.userData.screen;

  const stand = cylinder(0.12, 0.2, 0.5, 16, palette.deskLeg);
  stand.position.set(0, 1.85, -0.7);
  group.add(stand);

  // Peripherals: a keyboard centred in front of the monitor and a mouse on
  // a small pad to one side. These are purely visual — they never carry state.
  const keyboard = makeKeyboard(palette);
  keyboard.position.set(0, 1.62, 0.35);
  group.add(keyboard);

  const mousePad = box(1.1, 0.02, 0.75, palette.mousePad || '#1a1a24');
  mousePad.position.set(1.35, 1.61, 0.35);
  mousePad.castShadow = false;
  group.add(mousePad);

  const mouse = makeMouse(palette);
  mouse.position.set(1.35, 1.67, 0.35);
  group.add(mouse);

  return group;
}

function makeKeyboard(palette) {
  const group = new THREE.Group();
  const board = roundedSlab(2.2, 0.06, 0.85, palette.keyboard || '#24242e', 0.08);
  board.position.y = 0.03;
  board.castShadow = false;
  group.add(board);
  // A few rows of "keys" drawn as thin light strips on the board top.
  const keyMat = material(palette.keyboardKey || '#9a9aa8', { rough: 0.5, metal: 0.1 });
  for (let row = 0; row < 4; row += 1) {
    const keyRow = new THREE.Mesh(
      new THREE.PlaneGeometry(1.9, 0.08),
      keyMat,
    );
    keyRow.rotation.x = -Math.PI / 2;
    keyRow.position.set(0, 0.065, -0.24 + row * 0.16);
    group.add(keyRow);
  }
  return group;
}

function makeMouse(palette) {
  const group = new THREE.Group();
  const body = new THREE.Mesh(
    new THREE.SphereGeometry(0.22, 12, 10),
    material(palette.mouse || '#c9c9d6', { rough: 0.35, metal: 0.1 }),
  );
  body.scale.set(1, 0.55, 1.35);
  body.position.y = 0.05;
  body.castShadow = true;
  group.add(body);
  return group;
}

/** Monitor panel. Its canvas texture is redrawn by `drawScreen`. */
function makeScreen(palette) {
  const group = new THREE.Group();

  const bezel = roundedPanel(2.9, 1.8, 0.12, palette.screenBezel, 0.12);
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

/**
 * Fill a working screen with bright, shifting "activity" so the monitor reads
 * as alive. The palette's screenBg is replaced with near-white; thin moving
 * bars and scattered dots stand in for code or data scrolling past. `phase`
 * is time in seconds; `seed` keeps different desks from mirroring each other.
 */
export function drawActiveScreen(screen, palette, phase, seed) {
  if (!screen || !screen.ctx) return;
  const { ctx, canvas, texture } = screen;
  ctx.fillStyle = palette.screenActiveBg || '#f7f7fb';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const rnd = mulberry32(seed || 1);
  const cols = ['#e0527d', '#3f7fd4', '#4fae5e', '#e0a934', '#9457c7', '#2f9e8f'];
  const barCount = 6;
  for (let i = 0; i < barCount; i += 1) {
    const speed = 18 + rnd() * 34;
    const y = 8 + rnd() * (canvas.height - 16);
    const h = 2 + rnd() * 4;
    const w = 20 + rnd() * 80;
    const x = ((phase * speed + rnd() * 200) % (canvas.width + w * 2)) - w;
    ctx.fillStyle = cols[i % cols.length];
    ctx.globalAlpha = 0.55;
    ctx.fillRect(x, y, w, h);
  }
  ctx.globalAlpha = 1;

  // A few blinking indicator dots in the top-right corner.
  for (let i = 0; i < 3; i += 1) {
    const on = Math.sin(phase * (3 + i) + seed) > 0;
    ctx.fillStyle = on ? palette.screenText : palette.screenBezel;
    ctx.beginPath();
    ctx.arc(canvas.width - 14 - i * 12, 12, 2.5, 0, Math.PI * 2);
    ctx.fill();
  }
  texture.needsUpdate = true;
}

function mulberry32(a) {
  return function () {
    let t = (a += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* ---------- chair ---------- */

/* ---------- cubicle ---------- */

// Desk-local frame, measured from the floor the cubicle stands on: the
// monitor sits at -z, the chair at +z (1.9), and a subagent walks in from +z
// (|x| <= 1.4, from up to z ~5). Heights are proportioned to the desk as it
// shows above the raised platform (desk top ~1.0 above that floor). The cubicle
// encloses desk and chair on all four sides at one height, with an opening in
// the front wall over that walk-in path.
const CUBICLE_HALF_WIDTH = 3.1;
const CUBICLE_BACK_Z = -1.75;
const CUBICLE_FRONT_Z = 3.0;
const CUBICLE_DOOR_HALF = 1.8;
const CUBICLE_HEIGHT = 1.75;
// Solid lower panel; frosted glass above it keeps the desk and its worker
// visible over the near walls from the isometric camera.
const CUBICLE_SOLID_HEIGHT = 0.9;
const CUBICLE_POST = 0.12;
const CUBICLE_RAIL = 0.08;
const CUBICLE_PANEL = 0.07;
const CUBICLE_ACCENT_HEIGHT = 0.03;
const CUBICLE_RUG_MARGIN = 0.25;
// Accent glow, as emissive intensity. Both stay well under the bloom pass'
// threshold: a crisp coloured line, never a halo competing with the pods.
export const CUBICLE_ACCENT_IDLE = 0.12;
export const CUBICLE_ACCENT_ACTIVE = 0.55;

/** The wall runs, as [x1, z1, x2, z2] in desk-local space. */
function cubicleWallRuns() {
  const w = CUBICLE_HALF_WIDTH;
  const b = CUBICLE_BACK_Z;
  const f = CUBICLE_FRONT_Z;
  const d = CUBICLE_DOOR_HALF;
  return [
    [-w, b, w, b],   // back
    [-w, b, -w, f],  // left
    [w, b, w, f],    // right
    [-w, f, -d, f],  // front, left of the opening
    [d, f, w, f],    // front, right of the opening
  ];
}

/**
 * Merge positioned parts into one non-indexed geometry (position + normal),
 * so a whole cubicle costs one draw call per material instead of ~30.
 */
function mergeParts(parts) {
  const positions = [];
  const normals = [];
  const normalMatrix = new THREE.Matrix3();
  const v = new THREE.Vector3();
  parts.forEach(({ geo, matrix }) => {
    const g = geo.index ? geo.toNonIndexed() : geo;
    const pos = g.getAttribute('position');
    const nor = g.getAttribute('normal');
    normalMatrix.getNormalMatrix(matrix);
    for (let i = 0; i < pos.count; i += 1) {
      v.fromBufferAttribute(pos, i).applyMatrix4(matrix);
      positions.push(v.x, v.y, v.z);
      v.fromBufferAttribute(nor, i).applyMatrix3(normalMatrix).normalize();
      normals.push(v.x, v.y, v.z);
    }
    if (g !== geo) g.dispose();
    geo.dispose();
  });
  const merged = new THREE.BufferGeometry();
  merged.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  merged.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));
  merged.computeBoundingBox();
  merged.computeBoundingSphere();
  return merged;
}

/** A box part centred at (x, y, z), turned to run along its wall. */
function cubiclePart(width, height, depth, x, y, z, angle) {
  const m = new THREE.Matrix4().makeRotationY(angle || 0);
  m.setPosition(x, y, z);
  return { geo: new THREE.BoxGeometry(width, height, depth), matrix: m };
}

/** The four shared cubicle geometries: panels, frame, glass, accent. */
function cubicleGeometries() {
  return geometry('cubicle|v2', () => {
    const panels = [];
    const frame = [];
    const glass = [];
    const accent = [];
    const posts = new Map();
    const glassHeight = CUBICLE_HEIGHT - CUBICLE_SOLID_HEIGHT - CUBICLE_RAIL;
    cubicleWallRuns().forEach(([x1, z1, x2, z2]) => {
      const length = Math.hypot(x2 - x1, z2 - z1);
      // Wall runs along x or z; Box width is its local x, so turn z-runs.
      const angle = Math.abs(x2 - x1) > Math.abs(z2 - z1) ? 0 : Math.PI / 2;
      const cx = (x1 + x2) / 2;
      const cz = (z1 + z2) / 2;
      const inner = Math.max(0.01, length - CUBICLE_POST);
      panels.push(cubiclePart(inner, CUBICLE_SOLID_HEIGHT, CUBICLE_PANEL, cx, CUBICLE_SOLID_HEIGHT / 2, cz, angle));
      frame.push(cubiclePart(inner, CUBICLE_RAIL, CUBICLE_POST * 0.8, cx, CUBICLE_SOLID_HEIGHT + CUBICLE_RAIL / 2, cz, angle));
      glass.push(cubiclePart(inner, glassHeight, 0.03, cx, CUBICLE_SOLID_HEIGHT + CUBICLE_RAIL + glassHeight / 2, cz, angle));
      frame.push(cubiclePart(length + CUBICLE_POST, CUBICLE_RAIL, CUBICLE_POST, cx, CUBICLE_HEIGHT - CUBICLE_RAIL / 2, cz, angle));
      accent.push(cubiclePart(length + CUBICLE_POST, CUBICLE_ACCENT_HEIGHT, CUBICLE_POST + 0.01, cx, CUBICLE_HEIGHT + CUBICLE_ACCENT_HEIGHT / 2, cz, angle));
      [[x1, z1], [x2, z2]].forEach(([x, z]) => posts.set(`${x}|${z}`, [x, z]));
    });
    posts.forEach(([x, z]) => {
      frame.push(cubiclePart(CUBICLE_POST, CUBICLE_HEIGHT, CUBICLE_POST, x, CUBICLE_HEIGHT / 2, z, 0));
    });
    return {
      panels: mergeParts(panels),
      frame: mergeParts(frame),
      glass: mergeParts(glass),
      accent: mergeParts(accent),
    };
  });
}

function cubicleAccentMaterial(accent, active) {
  return material(accent, {
    rough: 0.5, emissive: accent,
    ei: active ? CUBICLE_ACCENT_ACTIVE : CUBICLE_ACCENT_IDLE,
  });
}

/**
 * A framed office cubicle around a desk: solid lower panels, frosted glass
 * above, a thin rail in the platform's colour along the top, and a rug in a
 * darker shade of the platform under it. `setCubicleActive` brightens the
 * rail while the desk's subagent works.
 */
export function makeCubicle(palette, accent) {
  const group = new THREE.Group();
  const accentColor = accent || palette.cubicleAccent || '#8a96aa';
  const geos = cubicleGeometries();

  const panels = new THREE.Mesh(geos.panels, material(palette.cubiclePanel || '#9aa3b2', { rough: 0.9 }));
  panels.castShadow = true;
  panels.receiveShadow = true;
  const frame = new THREE.Mesh(geos.frame, material(palette.cubicleFrame || '#4b5363', { rough: 0.55, metal: 0.25 }));
  frame.castShadow = true;
  frame.receiveShadow = true;
  const glass = new THREE.Mesh(geos.glass, material(palette.cubicleGlass || '#dbe4f0', {
    rough: 0.2, transparent: true, opacity: palette.cubicleGlassOpacity ?? 0.16,
  }));
  glass.renderOrder = 1;
  const strip = new THREE.Mesh(geos.accent, cubicleAccentMaterial(accentColor, false));
  [panels, frame, glass, strip].forEach(mesh => group.add(mesh));

  // A step darker than the platform's own top (the blend makePod paints), so
  // it reads as carpet on that floor rather than a second colour.
  const floorColor = accent && palette.podTop ? mixColor(palette.podTop, accent, 0.62) : (palette.podTop || accentColor);
  const rugColor = mixColor(floorColor, palette.cubicleRugShade || '#000000', palette.cubicleRugMix ?? 0.35);
  const rugWidth = CUBICLE_HALF_WIDTH * 2 + CUBICLE_RUG_MARGIN * 2;
  const rugDepth = CUBICLE_FRONT_Z - CUBICLE_BACK_Z + CUBICLE_RUG_MARGIN * 2;
  const rug = roundedSlab(rugWidth, 0.04, rugDepth, rugColor, 0.3);
  rug.position.set(0, 0.02, (CUBICLE_BACK_Z + CUBICLE_FRONT_Z) / 2);
  rug.castShadow = false;
  group.add(rug);

  group.userData.cubicle = { accent: accentColor, active: false, strips: [strip] };
  return group;
}

export function setCubicleActive(cubicle, active) {
  const state = cubicle && cubicle.userData && cubicle.userData.cubicle;
  if (!state || state.active === !!active) return;
  state.active = !!active;
  const mat = cubicleAccentMaterial(state.accent, state.active);
  state.strips.forEach(strip => { strip.material = mat; });
}

export function makeChair(palette) {
  const group = new THREE.Group();
  const seat = roundedSlab(1.5, 0.2, 1.4, palette.chair, 0.2);
  seat.position.y = 1.0;
  group.add(seat);
  const back = roundedPanel(1.5, 1.2, 0.2, palette.chair, 0.22);
  back.position.set(0, 1.6, 0.6);
  group.add(back);
  const post = cylinder(0.12, 0.12, 1.0, 16, palette.deskLeg);
  post.position.y = 0.5;
  group.add(post);
  const foot = cylinder(0.7, 0.75, 0.12, 24, palette.deskLeg);
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
    geometry('head', () => new THREE.SphereGeometry(0.45, 24, 18)), skin,
  );
  skull.castShadow = true;
  head.add(skull);
  const hair = new THREE.Mesh(
    geometry('hair', () => new THREE.SphereGeometry(
      0.47, 24, 14, 0, Math.PI * 2, 0, Math.PI * 0.55,
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

  // ---- status-adjacent animations --------------------------------------
  // These poses are driven by real Hermes state, not idle decoration.
  // `sleep`  : running but with no tool activity for a while.
  // `celebrate`: just completed — a brief arms-up gesture before settling to `done`.
  // `frustrated`: failed / error — hands on head.
  sleep:       { shoulderX: -0.25, shoulderZ: 0.10, headX: -0.55, torsoX: -0.10, lift: 0.15 },
  // Used only while Hermes reports active delegates: a visible directing
  // gesture, not decorative activity.
  orchestrate: { shoulderX: -0.82, shoulderZ: 0.34, headX: -0.04, torsoX: 0.10, lift: 0.08 },
  celebrate:   { shoulderX: -2.80, shoulderZ: -0.55, headX: -0.25, torsoX: -0.12, lift: 0.20 },
  frustrated:  { shoulderX: -0.60, shoulderZ: 0.55, headX: 0.45, torsoX: 0.22, lift: 0.05 },

  // ---- idle behaviours -------------------------------------------------
  // Decoration, not state. These only ever play over `work` — a figure that
  // is thinking rather than mid-tool-call — and each one is visually distinct
  // from every pose above that *means* something, so nobody reads a stretch
  // as an error or a sip as a completion.
  //
  // `lean` and `sip` keep the figure at the desk; `stretch` stands it up.
  lean:    { shoulderX: -0.55, shoulderZ: -0.22, headX: 0.20, torsoX: -0.16, lift: 0 },
  sip:     { shoulderX: -1.70, shoulderZ: 0.55, headX: -0.14, torsoX: 0.02, lift: 0 },
  // Keep raised arms clear of the head silhouette; the older, near-backward
  // shoulder angle visibly intersected it in an isometric overview.
  stretch: { shoulderX: -1.88, shoulderZ: -0.38, headX: -0.12, torsoX: -0.05, lift: 0.24 },
  glance:  { shoulderX: -1.05, shoulderZ: 0.16, headX: 0.05, torsoX: 0.04, lift: 0, headY: 0.85 },
  coffee:  { shoulderX: -1.75, shoulderZ: 0.45, headX: -0.10, torsoX: 0.04, lift: 0 },
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
export function poseWorker(person, pose, elapsed, dt, opts) {
  const joints = person && person.userData && person.userData.joints;
  if (!joints) return;
  // A desk worker's legs are tucked behind furniture. A figure with no desk
  // (the conductor, pausing on its plinth or orchestrating) stands on them.
  const standing = !!(opts && opts.standing);
  if (joints.legs) joints.legs.visible = standing;
  // An idle behaviour may be playing over plain work; everything below drives
  // toward whichever pose that resolves to.
  const played = idlePoseFor(person.userData, pose, elapsed * 1000);
  const target = poseTargets(played);
  // Exponential easing is frame-rate independent: a busy browser and a
  // 120Hz display settle through the same smooth pose instead of visibly
  // changing speed with their frame time.
  const k = 1 - Math.exp(-Math.min(0.1, Math.max(0, dt)) * 14);

  const typing = played === 'work' || played === 'tool' || played === 'orchestrate';
  // The former jitter disappeared at the normal Office overview scale. Keep
  // motion desk-bound, but make active work and orchestration legible.
  const motion = played === 'orchestrate' ? 0.22 : 0.18;
  const jitterL = typing ? Math.sin(elapsed * 9.0) * motion : 0;
  const jitterR = typing ? Math.sin(elapsed * 7.4 + 1.3) * (motion * 1.08) : 0;
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
  if (standing && joints.hipL && joints.hipR) {
    // Settle out of the last stride rather than freezing mid-swing.
    joints.hipL.rotation.x = lerp(joints.hipL.rotation.x, 0, k);
    joints.hipR.rotation.x = lerp(joints.hipR.rotation.x, 0, k);
  }
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

/* ---------- chat bubble (mood) ---------- */

/** Mood icons shown above a worker's head for a moment. */
export const MOOD_ICONS = {
  sleep: 'Zzz',
  work: '⚡',
  tool: '🛠',
  coffee: '☕',
  done: '✓',
  error: '✕',
  fire: '🔥',
};

/**
 * A small speech-style bubble that pops up above a worker to express a mood.
 * Returns a Sprite so it always faces the camera.
 */
export function makeChatBubble(palette) {
  const canvas = document.createElement('canvas');
  canvas.width = 128;
  canvas.height = 96;
  const ctx = canvas.getContext('2d');
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: texture, transparent: true, depthWrite: false,
  }));
  sprite.scale.set(1.6, 1.2, 1);
  sprite.position.set(0, 2.9, 0);
  sprite.visible = false;
  sprite.userData.bubble = { canvas, ctx, texture, icon: '' };
  return sprite;
}

export function drawChatBubble(sprite, palette, icon) {
  const bubble = sprite && sprite.userData && sprite.userData.bubble;
  if (!bubble) return;
  const { ctx, canvas, texture } = bubble;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const pad = 12;
  const r = 18;
  const w = canvas.width - pad * 2;
  const h = canvas.height - pad * 2 - 10;
  const x = pad;
  const y = pad;

  ctx.fillStyle = palette.bubbleBg || 'rgba(20,20,30,0.88)';
  ctx.strokeStyle = palette.bubbleStroke || 'rgba(180,180,200,0.55)';
  ctx.lineWidth = 2;
  roundRectPath(ctx, x, y, w, h, r);
  ctx.fill();
  ctx.stroke();

  // Tiny tail pointing down toward the worker's head.
  ctx.beginPath();
  ctx.moveTo(canvas.width / 2 - 8, y + h);
  ctx.lineTo(canvas.width / 2, y + h + 10);
  ctx.lineTo(canvas.width / 2 + 8, y + h);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();

  ctx.font = '700 42px ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = palette.bubbleText || '#f2f2f7';
  ctx.fillText(String(icon || ''), canvas.width / 2, (y + h / 2) + 2);

  bubble.icon = icon;
  texture.needsUpdate = true;
}

function roundRectPath(ctx, x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.lineTo(x + w - rr, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + rr);
  ctx.lineTo(x + w, y + h - rr);
  ctx.quadraticCurveTo(x + w, y + h, x + w - rr, y + h);
  ctx.lineTo(x + rr, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - rr);
  ctx.lineTo(x, y + rr);
  ctx.quadraticCurveTo(x, y, x + rr, y);
  ctx.closePath();
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

/* ---------- conductor pattern ---------- */

/**
 * Generate a canvas texture for the central Conductor plinth. A dark slab with
 * a subtle geometric emblem reads as a deliberate landmark rather than an
 * empty platform.
 */
export function makeConductorTexture(palette, size) {
  const canvas = document.createElement('canvas');
  const s = size || 512;
  canvas.width = s;
  canvas.height = s;
  const ctx = canvas.getContext('2d');

  const base = palette.podTop;
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, s, s);

  const accent = palette.conductor || '#e2e8f0';
  // Very faint grid so it does not fight with the app UI.
  ctx.save();
  ctx.strokeStyle = accent;
  ctx.globalAlpha = 0.09;
  ctx.lineWidth = 1;
  const step = s / 16;
  for (let i = 0; i <= s; i += step) {
    ctx.beginPath();
    ctx.moveTo(i, 0);
    ctx.lineTo(i, s);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(0, i);
    ctx.lineTo(s, i);
    ctx.stroke();
  }
  ctx.restore();

  const cx = s / 2;
  const cy = s / 2;

  // Outer ring.
  ctx.save();
  ctx.strokeStyle = accent;
  ctx.globalAlpha = 0.28;
  ctx.lineWidth = Math.max(2, s / 128);
  ctx.beginPath();
  ctx.arc(cx, cy, s * 0.38, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();

  // Inner disc.
  ctx.save();
  ctx.fillStyle = accent;
  ctx.globalAlpha = 0.12;
  ctx.beginPath();
  ctx.arc(cx, cy, s * 0.18, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();

  // Center dot.
  ctx.save();
  ctx.fillStyle = accent;
  ctx.globalAlpha = 0.45;
  ctx.beginPath();
  ctx.arc(cx, cy, s * 0.045, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();

  // Corner tick marks.
  ctx.save();
  ctx.strokeStyle = accent;
  ctx.globalAlpha = 0.18;
  ctx.lineWidth = Math.max(2, s / 128);
  const tickInset = s * 0.08;
  const tickLen = s * 0.06;
  [
    [[tickInset, tickInset], [tickInset + tickLen, tickInset]],
    [[tickInset, tickInset], [tickInset, tickInset + tickLen]],
    [[s - tickInset, tickInset], [s - tickInset - tickLen, tickInset]],
    [[s - tickInset, tickInset], [s - tickInset, tickInset + tickLen]],
    [[tickInset, s - tickInset], [tickInset + tickLen, s - tickInset]],
    [[tickInset, s - tickInset], [tickInset, s - tickInset - tickLen]],
    [[s - tickInset, s - tickInset], [s - tickInset - tickLen, s - tickInset]],
    [[s - tickInset, s - tickInset], [s - tickInset, s - tickInset - tickLen]],
  ].forEach(([[x1, y1], [x2, y2]]) => {
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
  });
  ctx.restore();

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return { canvas, ctx, texture };
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
    const glow = obj.userData && obj.userData.podGlow;
    if (glow) {
      glow.geometry.dispose();
      glow.material.dispose();
    }
    const bubble = obj.userData && obj.userData.bubble;
    if (bubble) {
      bubble.texture.dispose();
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
