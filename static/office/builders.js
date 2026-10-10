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
    _sharedGeometries.add(geo);
  }
  return geo;
}
const _sharedGeometries = new WeakSet();

/**
 * Merge a static group's meshes into one mesh per material (and shadow
 * setting), so a pod's scenery or a desk costs a handful of draw calls
 * instead of dozens -- the Business floor drew ~1,300 a frame before this.
 * Textured meshes (live screens, icon plaques), points, sprites and anything
 * tagged `userData.noMerge` (it moves) are left as they are.
 *
 * With `cacheKey`, the merged geometries are kept in the shared cache, so the
 * same scenery rebuilt on the next sync is not merged again; without one,
 * they belong to this group and disposeTree releases them.
 */
export function mergeStatic(group, cacheKey) {
  group.updateMatrixWorld(true);
  const rootInverse = new THREE.Matrix4().copy(group.matrixWorld).invert();
  const buckets = new Map();
  const doomed = [];
  group.traverse(obj => {
    if (!obj.isMesh || obj === group) return;
    let skip = false;
    for (let o = obj; o && o !== group; o = o.parent) if (o.userData && o.userData.noMerge) skip = true;
    const mat = obj.material;
    // Textured meshes merge only when their material says it is shared and
    // static (a glow card, a fixed console screen); live screens keep theirs.
    const textured = !!mat.map;
    if (skip || Array.isArray(mat) || !obj.geometry.getAttribute('normal')) return;
    if (textured && !(mat.userData && mat.userData.mergeable && obj.geometry.getAttribute('uv'))) return;
    const key = `${mat.uuid}|${obj.castShadow ? 1 : 0}`;
    if (!buckets.has(key)) buckets.set(key, { material: mat, castShadow: obj.castShadow, receiveShadow: obj.receiveShadow, parts: [] });
    buckets.get(key).parts.push({ geometry: obj.geometry, color: mat.color, matrix: new THREE.Matrix4().multiplyMatrices(rootInverse, obj.matrixWorld) });
    doomed.push(obj);
  });
  doomed.forEach(obj => {
    obj.removeFromParent();
    if (!_sharedGeometries.has(obj.geometry)) obj.geometry.dispose();
  });
  // Every plain opaque colour (no glow, glass, texture or clearcoat) folds
  // into one vertex-coloured mesh per shadow setting, so a desk or a pod's
  // scenery costs a draw call or two for all its colours, not one each. The
  // parts keep their colours; only their individual roughness is averaged
  // away, which at this scale does not show.
  const plain = m => m.isMeshStandardMaterial && !m.isMeshPhysicalMaterial && !m.transparent && !m.map
    && !m.vertexColors && (!m.emissive || m.emissive.getHex() === 0 || !m.emissiveIntensity);
  const colored = new Map();
  [...buckets].forEach(([key, bucket]) => {
    if (!plain(bucket.material)) return;
    buckets.delete(key);
    const ck = `colored|${bucket.castShadow ? 1 : 0}`;
    if (!colored.has(ck)) colored.set(ck, { material: vertexColoredMaterial(), castShadow: bucket.castShadow, receiveShadow: true, parts: [], colored: true });
    colored.get(ck).parts.push(...bucket.parts);
  });
  colored.forEach((bucket, key) => buckets.set(key, bucket));
  let index = 0;
  buckets.forEach(bucket => {
    const build = () => {
      // Typed arrays written in place (no per-vertex objects): indexed parts
      // keep their index, offset into the merged vertex range.
      let vertexCount = 0;
      let indexCount = 0;
      bucket.parts.forEach(({ geometry: g }) => {
        const n = g.getAttribute('position').count;
        vertexCount += n;
        indexCount += g.index ? g.index.count : n;
      });
      const positions = new Float32Array(vertexCount * 3);
      const normals = new Float32Array(vertexCount * 3);
      const colors = bucket.colored ? new Float32Array(vertexCount * 3) : null;
      const withUv = !!bucket.material.map;
      const uvs = withUv ? new Float32Array(vertexCount * 2) : null;
      const indices = vertexCount > 65535 ? new Uint32Array(indexCount) : new Uint16Array(indexCount);
      const nm = new THREE.Matrix3();
      let vo = 0;
      let io = 0;
      bucket.parts.forEach(({ geometry: g, matrix, color }) => {
        const pos = g.getAttribute('position').array;
        const nor = g.getAttribute('normal').array;
        const n = g.getAttribute('position').count;
        const e = matrix.elements;
        nm.getNormalMatrix(matrix);
        const m = nm.elements;
        for (let i = 0; i < n; i += 1) {
          const x = pos[i * 3], y = pos[i * 3 + 1], z = pos[i * 3 + 2];
          const o = (vo + i) * 3;
          positions[o] = e[0] * x + e[4] * y + e[8] * z + e[12];
          positions[o + 1] = e[1] * x + e[5] * y + e[9] * z + e[13];
          positions[o + 2] = e[2] * x + e[6] * y + e[10] * z + e[14];
          const nx = nor[i * 3], ny = nor[i * 3 + 1], nz = nor[i * 3 + 2];
          let ox = m[0] * nx + m[3] * ny + m[6] * nz;
          let oy = m[1] * nx + m[4] * ny + m[7] * nz;
          let oz = m[2] * nx + m[5] * ny + m[8] * nz;
          const len = Math.hypot(ox, oy, oz) || 1;
          normals[o] = ox / len; normals[o + 1] = oy / len; normals[o + 2] = oz / len;
        }
        if (colors) for (let i = 0; i < n; i += 1) { colors[(vo + i) * 3] = color.r; colors[(vo + i) * 3 + 1] = color.g; colors[(vo + i) * 3 + 2] = color.b; }
        if (uvs) uvs.set(g.getAttribute('uv').array.subarray(0, n * 2), vo * 2);
        if (g.index) {
          const idx = g.index.array;
          for (let i = 0; i < idx.length; i += 1) indices[io + i] = idx[i] + vo;
          io += idx.length;
        } else {
          for (let i = 0; i < n; i += 1) indices[io + i] = vo + i;
          io += n;
        }
        vo += n;
      });
      const merged = new THREE.BufferGeometry();
      merged.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      merged.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
      if (uvs) merged.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
      if (colors) merged.setAttribute('color', new THREE.BufferAttribute(colors, 3));
      merged.setIndex(new THREE.BufferAttribute(indices, 1));
      merged.computeBoundingSphere();
      return merged;
    };
    const merged = cacheKey ? geometry(`merged2|${cacheKey}|${index}|${bucket.material.uuid}`, build) : build();
    const mesh = new THREE.Mesh(merged, bucket.material);
    mesh.castShadow = bucket.castShadow;
    mesh.receiveShadow = bucket.receiveShadow;
    if (!cacheKey) mesh.userData.mergedGeometry = true;
    group.add(mesh);
    index += 1;
  });
  // Empty sub-groups left behind are harmless but cost a traversal each frame.
  const empties = [];
  group.traverse(obj => { if (obj !== group && obj.isGroup && !obj.children.length) empties.push(obj); });
  empties.forEach(obj => obj.removeFromParent());
  return group;
}

function vertexColoredMaterial() {
  let mat = _materials.get('vertex-colored');
  if (!mat) {
    mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.7, metalness: 0.08 });
    _materials.set('vertex-colored', mat);
  }
  return mat;
}

/**
 * Merge a static group into ONE mesh, whatever its colours: each part's
 * material colour is baked into vertex colours and drawn with one shared
 * vertex-coloured material. For small multi-coloured things that move as a
 * unit (a figure's limb), where mergeStatic would still leave one draw per
 * colour. Textures, emissive and per-part finish are given up for that.
 */
export function mergeColored(group, cacheKey, opts) {
  const options = opts || {};
  group.updateMatrixWorld(true);
  const rootInverse = new THREE.Matrix4().copy(group.matrixWorld).invert();
  const parts = [];
  group.traverse(obj => {
    if (!obj.isMesh || obj === group) return;
    parts.push({ geometry: obj.geometry, color: obj.material.color || new THREE.Color('#ffffff'), matrix: new THREE.Matrix4().multiplyMatrices(rootInverse, obj.matrixWorld) });
  });
  const build = () => {
    let vertexCount = 0;
    let indexCount = 0;
    parts.forEach(({ geometry: g }) => {
      const n = g.getAttribute('position').count;
      vertexCount += n;
      indexCount += g.index ? g.index.count : n;
    });
    const positions = new Float32Array(vertexCount * 3);
    const normals = new Float32Array(vertexCount * 3);
    const colors = new Float32Array(vertexCount * 3);
    const indices = vertexCount > 65535 ? new Uint32Array(indexCount) : new Uint16Array(indexCount);
    const nm = new THREE.Matrix3();
    let vo = 0;
    let io = 0;
    parts.forEach(({ geometry: g, color, matrix }) => {
      const pos = g.getAttribute('position').array;
      const nor = g.getAttribute('normal').array;
      const n = g.getAttribute('position').count;
      const e = matrix.elements;
      nm.getNormalMatrix(matrix);
      const m = nm.elements;
      for (let i = 0; i < n; i += 1) {
        const x = pos[i * 3], y = pos[i * 3 + 1], z = pos[i * 3 + 2];
        const o = (vo + i) * 3;
        positions[o] = e[0] * x + e[4] * y + e[8] * z + e[12];
        positions[o + 1] = e[1] * x + e[5] * y + e[9] * z + e[13];
        positions[o + 2] = e[2] * x + e[6] * y + e[10] * z + e[14];
        const nx = nor[i * 3], ny = nor[i * 3 + 1], nz = nor[i * 3 + 2];
        const ox = m[0] * nx + m[3] * ny + m[6] * nz;
        const oy = m[1] * nx + m[4] * ny + m[7] * nz;
        const oz = m[2] * nx + m[5] * ny + m[8] * nz;
        const len = Math.hypot(ox, oy, oz) || 1;
        normals[o] = ox / len; normals[o + 1] = oy / len; normals[o + 2] = oz / len;
        colors[o] = color.r; colors[o + 1] = color.g; colors[o + 2] = color.b;
      }
      if (g.index) {
        const idx = g.index.array;
        for (let i = 0; i < idx.length; i += 1) indices[io + i] = idx[i] + vo;
        io += idx.length;
      } else {
        for (let i = 0; i < n; i += 1) indices[io + i] = vo + i;
        io += n;
      }
      vo += n;
    });
    const merged = new THREE.BufferGeometry();
    merged.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    merged.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
    merged.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    merged.setIndex(new THREE.BufferAttribute(indices, 1));
    merged.computeBoundingSphere();
    return merged;
  };
  const geo = geometry(`colored|${cacheKey}`, build);
  parts.forEach(({ geometry: g }) => { if (!_sharedGeometries.has(g)) g.dispose(); });
  const mesh = new THREE.Mesh(geo, vertexColoredMaterial());
  mesh.castShadow = options.castShadow !== false;
  mesh.receiveShadow = false;
  return mesh;
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
export function makePod(width, depth, palette, tint, opts) {
  const options = opts || {};
  const group = new THREE.Group();
  const topColor = tint ? mixColor(palette.podTop, tint, 0.62) : (options.top || palette.podTop);
  const isUntinted = !tint;
  // The reference look: a coloured slab on a glowing neon band, standing on
  // a dark base. Bases stay unmistakably dark in both palettes.
  const baseColor = '#1c2232';
  const footColor = '#121725';
  const radius = Math.min(width, depth) * 0.12;
  // The band glows in the department colour; an untinted platform (the
  // conductor hub, The Floor) takes `options.band` or stays dark.
  const bandColor = tint || options.band || null;

  function addLayer(name, height, color, y, layerOptions) {
    const lo = layerOptions || {};
    const layer = roundedPlatform(lo.layerWidth ?? width, lo.layerDepth ?? depth, height, color, Object.assign({
      // Flush faces: a bevel at every shared edge would recess each band into shadow.
      radius: lo.radius ?? radius, bevel: 0.001, bevelSegments: 1,
    }, lo));
    layer.position.set(0, y, 0);
    layer.userData.platformLayer = name;
    group.add(layer);
    return layer;
  }

  // Four flush layers: coloured top (its surface at y=0.6, where desks,
  // labels and bridges are laid out), the neon band, the dark base and its
  // footing.
  const topHeight = 1.2;
  const bandHeight = 0.42;
  const baseHeight = 1.1;
  const footHeight = 0.8;
  const lip = 0.12;
  const topMatOpts = isUntinted
    ? { physical: true, metal: 0.04, rough: 0.92, clearcoat: 0 }
    : { physical: true, metal: 0.06, rough: 0.72, clearcoat: 0.25 };
  // A faint tile pattern on the deck, so a platform reads as a floor rather
  // than a flat block of colour.
  const slab = addLayer('top', topHeight, topColor, 0, { material: deckMaterial(topColor, topMatOpts) });
  slab.castShadow = true;

  // The band owns its own material so a delivery can flare at one destination
  // only (scene.js's advanceDeliveryGlow adds to the idle intensity).
  const bandMaterial = material(bandColor || baseColor, { rough: 0.4, metal: 0.1 }).clone();
  // The same glow for every colour: bright colours (amber, teal) would bloom
  // into a halo at an intensity that leaves deep ones (purple, blue) barely
  // lit, so the intensity is set from the colour's own luminance.
  const bandLinear = new THREE.Color(bandColor || '#000000');
  const luminance = 0.2126 * bandLinear.r + 0.7152 * bandLinear.g + 0.0722 * bandLinear.b;
  // Kept just under the bloom threshold: the band itself glows (and pulses,
  // see scene.js) without spilling a halo onto the floor round the platform.
  // `glow: false` keeps the band's colour but lights nothing (The Floor).
  const idleIntensity = bandColor && options.glow !== false ? Math.min(3.5, Math.max(0.8, 0.72 / Math.max(0.05, luminance))) : 0;
  bandMaterial.emissive.set(bandColor || '#000000');
  bandMaterial.emissiveIntensity = idleIntensity;
  const bandY = -topHeight / 2 - bandHeight / 2;
  const delivery = addLayer('delivery', bandHeight, bandColor || baseColor, bandY, {
    layerWidth: width + lip, layerDepth: depth + lip, radius: radius + lip / 2, material: bandMaterial,
  });
  delivery.castShadow = false;
  delivery.userData.idleEmissiveIntensity = idleIntensity;
  delivery.userData.noGlow = options.glow === false;
  const baseY = bandY - bandHeight / 2 - baseHeight / 2;
  addLayer('upper-base', baseHeight, baseColor, baseY, {
    layerWidth: width + lip, layerDepth: depth + lip, radius: radius + lip / 2,
    matOpts: { rough: 0.9, metal: 0.05 },
  });
  addLayer('lower-base', footHeight, footColor, baseY - baseHeight / 2 - footHeight / 2, {
    layerWidth: width - 0.4, layerDepth: depth - 0.4, radius: Math.max(0.2, radius - 0.2),
    matOpts: { rough: 0.95, metal: 0.02 },
  });
  group.userData.deliveryLayer = delivery;
  return group;
}

function deckMaterial(color, opts) {
  const key = `deck|${color}|${opts.rough}|${opts.metal}|${opts.clearcoat}`;
  let mat = _materials.get(key);
  if (mat) return mat;
  let tex = _iconTextures.get('deck-tiles');
  // No canvas outside a browser (the node-driven tests): a plain deck.
  if (!tex && typeof document !== 'undefined') {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 128;
    const c = canvas.getContext('2d');
    c.fillStyle = '#ffffff';
    c.fillRect(0, 0, 128, 128);
    c.fillStyle = 'rgba(0,0,0,0.09)';
    c.fillRect(0, 0, 128, 2);
    c.fillRect(0, 0, 2, 128);
    c.fillStyle = 'rgba(255,255,255,0.0)';
    tex = new THREE.CanvasTexture(canvas);
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    // ExtrudeGeometry's UVs are in world units: one tile per 3 units.
    tex.repeat.set(1 / 3, 1 / 3);
    tex.anisotropy = 4;
    tex.colorSpace = THREE.SRGBColorSpace;
    _iconTextures.set('deck-tiles', tex);
  }
  mat = new THREE.MeshPhysicalMaterial({ color, map: tex || null, roughness: opts.rough, metalness: opts.metal, clearcoat: opts.clearcoat || 0, clearcoatRoughness: 0.15 });
  _materials.set(key, mat);
  return mat;
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
export function makeBridgeActivityChevrons(length, deckHeight, activeColor, panelDividers, skipFirst) {
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
  // The marker at the conductor's end (-z) sits right at the hub's edge, half
  // under it; a bridge that starts at the hub leaves it out.
  for (let i = skipFirst ? 1 : 0; i < boundaries.length - 1; i += 1) {
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
  // The dividers are merged into one mesh (one draw call per bridge, not one
  // per divider); their positions stay on `userData.panelDividers`.
  const panels = new THREE.Group();
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
    panel.castShadow = false;
    panel.receiveShadow = true;
    panels.add(panel);
  }
  group.add(mergeStatic(panels, `bridge-panels|${dimensions.depth.toFixed(3)}|${panelColor}`));
  group.userData.panelDividers = panelDividers;

  // Two physical cables span the full deck from platform edge to platform
  // edge. Their animated current is toggled by scene activity state, never by
  // the destination-coloured side rails.
  group.add(makeBridgeActivityChevrons(dimensions.depth, dimensions.height, opts.railColor, panelDividers, !!opts.skipFirstChevron));

  // Glowing side rails along the outer edges only. The rail colour matches
  // the destination platform; the emissive material lets them bloom gently.
  const railColor = opts.railColor;
  if (railColor) {
    // The structural deck may run beneath a platform rim to remove any
    // visible gap. Keep the illuminated rails on the exposed bridge instead
    // of letting their taller profile appear to bleed across that platform.
    // `railTrims` gives each rail its own [start, end] trim; otherwise both
    // take railTrimStart / railTrimEnd.
    const both = [Math.max(0, opts.railTrimStart || 0), Math.max(0, opts.railTrimEnd || 0)];
    const trims = opts.railTrims || { left: both, right: both };
    const railSize = { width: 0.18, height: 0.22 };
    // A solid neon edge, as in the reference (it used to be a half-clear bar).
    const railMat = material(railColor, {
      emissive: railColor, ei: 0.9, metal: 0.1, rough: 0.35,
    });
    [['left', -1], ['right', 1]].forEach(([key, side]) => {
      const [trimStart, trimEnd] = trims[key];
      const depth = Math.max(0.1, dimensions.depth - trimStart - trimEnd).toFixed(3);
      const rail = new THREE.Mesh(
        geometry(`bridge-rail|${railSize.width}|${railSize.height}|${depth}`,
          () => new THREE.BoxGeometry(railSize.width, railSize.height, +depth)),
        railMat,
      );
      rail.position.set(
        side * (dimensions.width / 2 - railSize.width / 2),
        dimensions.height / 2 + railSize.height / 2 - 0.02,
        (trimStart - trimEnd) / 2,
      );
      rail.castShadow = false;
      group.add(rail);
    });

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

  // As in the reference: a light wood top on a dark drawer pedestal and a
  // slim panel leg, two monitors side by side.
  const top = roundedSlab(4.4, 0.18, 2.4, palette.deskTop, 0.12);
  top.position.y = 1.5;
  group.add(top);

  const pedestal = roundedSlab(1.2, 1.41, 2.1, palette.deskLeg, 0.06);
  pedestal.position.set(-1.45, 0.705, 0);
  group.add(pedestal);
  const drawerLine = material(shadeColor(palette.deskLeg, -0.08), { rough: 0.8 });
  [0.45, 0.95].forEach(y => {
    const line = new THREE.Mesh(geometry('drawer-line', () => new THREE.BoxGeometry(1.0, 0.03, 0.02)), drawerLine);
    line.position.set(-1.45, y, 1.06);
    group.add(line);
    const pull = box(0.32, 0.05, 0.05, palette.deskPull || '#cbd5e1');
    pull.position.set(-1.45, y + 0.22, 1.07);
    pull.castShadow = false;
    group.add(pull);
  });
  const leg = roundedSlab(0.16, 1.41, 2.1, palette.deskLeg, 0.04);
  leg.position.set(2.0, 0.705, 0);
  group.add(leg);

  // The live screen (a worker's tool call) on the left, a second monitor on the right.
  const screen = makeScreen(palette, 1.9, 1.22);
  screen.position.set(-0.98, 2.42, -0.72);
  screen.rotation.y = 0.14;
  group.add(screen);
  group.userData.screen = screen.userData.screen;
  const second = roundedPanel(1.9, 1.22, 0.1, palette.screenBezel, 0.08);
  second.position.set(0.98, 2.42, -0.72);
  second.rotation.y = -0.14;
  group.add(second);
  const secondGlow = new THREE.Mesh(geometry('second-screen', () => new THREE.PlaneGeometry(1.74, 1.06)),
    material(palette.screenBg || '#0a0a12', { emissive: palette.secondScreen || '#1e3a8a', ei: 0.55, rough: 0.4 }));
  secondGlow.position.set(0.98 + Math.sin(-0.14) * 0.06, 2.42, -0.72 + Math.cos(-0.14) * 0.06);
  secondGlow.rotation.y = -0.14;
  group.add(secondGlow);

  [-0.98, 0.98].forEach(x => {
    const stand = cylinder(0.08, 0.08, 0.5, 10, palette.screenBezel);
    stand.position.set(x, 1.85, -0.75);
    group.add(stand);
    const foot = roundedSlab(0.6, 0.05, 0.38, palette.screenBezel, 0.04);
    foot.position.set(x, 1.615, -0.75);
    foot.castShadow = false;
    group.add(foot);
  });

  // Peripherals: a keyboard centred in front of the monitors and a mouse on
  // a small pad to one side. These are purely visual — they never carry state.
  const keyboard = makeKeyboard(palette);
  keyboard.position.set(0, 1.6, 0.35);
  group.add(keyboard);

  const mousePad = box(1.1, 0.02, 0.75, palette.mousePad || '#1a1a24');
  mousePad.position.set(1.35, 1.6, 0.35);
  mousePad.castShadow = false;
  group.add(mousePad);

  const mouse = makeMouse(palette);
  mouse.position.set(1.35, 1.66, 0.35);
  group.add(mouse);

  // One mesh per material (the live screen stays its own textured mesh).
  return mergeStatic(group, `desk2|${palette.deskTop}|${palette.deskLeg}|${palette.screenBezel}|${palette.keyboard}`);
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
function makeScreen(palette, width, height) {
  const w = width || 2.9;
  const h = height || 1.8;
  const group = new THREE.Group();

  const bezel = roundedPanel(w, h, 0.12, palette.screenBezel, 0.1);
  group.add(bezel);

  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 160;
  const ctx = canvas.getContext('2d');
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;

  const panel = new THREE.Mesh(
    new THREE.PlaneGeometry(w - 0.18, h - 0.18),
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
/**
 * An idle desk's screen: a dim standby page (a soft gradient, a small ring
 * mark and a muted 'standby' line) rather than a black rectangle.
 */
export function drawStandbyScreen(screen, palette) {
  if (!screen || !screen.ctx) return;
  const { ctx, canvas, texture } = screen;
  const w = canvas.width, h = canvas.height;
  const g = ctx.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, '#0d1a33');
  g.addColorStop(1, '#070d1c');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = 'rgba(125,170,255,0.55)';
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.arc(w / 2, h * 0.42, Math.min(w, h) * 0.13, 0, Math.PI * 2);
  ctx.stroke();
  ctx.fillStyle = 'rgba(125,170,255,0.45)';
  ctx.beginPath();
  ctx.arc(w / 2, h * 0.42, Math.min(w, h) * 0.04, 0, Math.PI * 2);
  ctx.fill();
  ctx.font = '600 13px ui-monospace, SFMono-Regular, Menlo, monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillStyle = 'rgba(160,190,240,0.5)';
  ctx.fillText('standby', w / 2, h * 0.68);
  ctx.textAlign = 'start';
  texture.needsUpdate = true;
}

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
  // An office chair as in the reference: a five-spoke base on castors, a gas
  // lift, a padded seat, a tall back and armrests.
  const group = new THREE.Group();
  const frame = palette.chairFrame || '#1a1d26';
  for (let i = 0; i < 5; i += 1) {
    const a = i * (Math.PI * 2 / 5);
    const spoke = box(0.12, 0.08, 0.75, frame);
    spoke.position.set(Math.sin(a) * 0.36, 0.16, Math.cos(a) * 0.36);
    spoke.rotation.y = a;
    spoke.castShadow = false;
    group.add(spoke);
    const castor = cylinder(0.08, 0.08, 0.1, 8, frame);
    castor.rotation.z = Math.PI / 2;
    castor.position.set(Math.sin(a) * 0.7, 0.08, Math.cos(a) * 0.7);
    castor.castShadow = false;
    group.add(castor);
  }
  const lift = cylinder(0.08, 0.1, 0.8, 12, '#4b5161');
  lift.position.y = 0.55;
  group.add(lift);
  const seat = roundedSlab(1.5, 0.24, 1.4, palette.chair, 0.24);
  seat.position.y = 1.02;
  group.add(seat);
  const back = roundedPanel(1.4, 1.35, 0.2, palette.chair, 0.3);
  back.position.set(0, 1.85, 0.66);
  back.rotation.x = -0.08;
  group.add(back);
  const spine = box(0.16, 0.6, 0.12, frame);
  spine.position.set(0, 1.25, 0.66);
  group.add(spine);
  [-0.78, 0.78].forEach(x => {
    const arm = roundedSlab(0.14, 0.08, 0.8, frame, 0.04);
    arm.position.set(x, 1.45, 0.05);
    group.add(arm);
    const post = box(0.08, 0.38, 0.08, frame);
    post.position.set(x, 1.25, 0.3);
    group.add(post);
  });
  return mergeStatic(group, `chair2|${palette.chair}|${frame}`);
}

/* ---------- person ---------- */

/**
 * A worker. Joints hang off named groups so `poseWorker` can drive them
 * without rebuilding anything.
 *
 * @returns {THREE.Group} `userData.joints` = {shoulderL, shoulderR, head, torso}
 */
export function makePerson(palette, tint) {
  // An astronaut in a white suit: a helmet with a dark visor, a life-support
  // backpack, a chest control panel, gloves and boots. The worker's own
  // colour (`tint`) marks the shoulder patches, the backpack stripe and the
  // chest light, so figures stay tellable apart. The joint structure (and
  // so every pose) is the same as before; each joint's static parts are
  // merged, so a figure costs a handful of draw calls.
  const accent = hexOf(tint || palette.shirt, '#4f7ca8');
  const group = new THREE.Group();
  const suit = material('#eef1f6', { rough: 0.62 });
  const trim = material('#9aa3b3', { rough: 0.5, metal: 0.25 });
  const mark = material(accent, { rough: 0.5, emissive: accent, ei: 0.25 });
  const visorMat = material('#16223a', { physical: true, rough: 0.12, metal: 0.55, clearcoat: 1, emissive: '#1d3b70', ei: 0.25 });
  // Each joint's parts become one vertex-coloured mesh: a figure costs
  // seven draw calls (and six shadow draws), not one per colour per joint.
  const merged = (key, parts) => {
    const g = new THREE.Group();
    parts.forEach(m => g.add(m));
    return mergeColored(g, `astro|${key}|${accent}`);
  };

  const torso = new THREE.Group();
  torso.position.y = 1.55;
  group.add(torso);

  const chest = capsule(0.44, 0.78, suit);
  chest.position.y = 0.4;
  const panel = roundedPanel(0.42, 0.28, 0.08, trim, 0.05);
  panel.position.set(0, 0.48, 0.44);
  const light = box(0.1, 0.07, 0.04, mark);
  light.position.set(-0.1, 0.53, 0.5);
  const knob = box(0.1, 0.07, 0.04, '#5b6474');
  knob.position.set(0.1, 0.53, 0.5);
  const belt = new THREE.Mesh(geometry('astro-belt', () => new THREE.TorusGeometry(0.43, 0.06, 8, 24)), trim);
  belt.rotation.x = Math.PI / 2;
  belt.position.y = -0.02;
  const pack = roundedSlab(0.74, 0.92, 0.34, '#d6dbe3', 0.1);
  pack.position.set(0, 0.42, -0.5);
  const packStripe = box(0.76, 0.08, 0.36, mark);
  packStripe.position.set(0, 0.62, -0.5);
  const collar = new THREE.Mesh(geometry('astro-collar', () => new THREE.TorusGeometry(0.3, 0.08, 8, 24)), trim);
  collar.rotation.x = Math.PI / 2;
  collar.position.y = 0.86;
  torso.add(merged('torso', [chest, panel, light, knob, belt, pack, packStripe, collar]));

  const arm = side => {
    const shoulder = new THREE.Group();
    shoulder.position.set(side * 0.52, 0.72, 0);
    const sleeve = capsule(0.16, 0.58, suit);
    sleeve.position.y = -0.4;
    const patch = cylinder(0.12, 0.12, 0.04, 16, mark);
    patch.rotation.z = Math.PI / 2;
    patch.position.set(side * 0.16, -0.08, 0);
    const cuff = cylinder(0.17, 0.17, 0.08, 16, trim);
    cuff.position.y = -0.72;
    const glove = new THREE.Mesh(geometry('astro-glove', () => new THREE.SphereGeometry(0.15, 14, 10)), trim);
    glove.position.y = -0.84;
    shoulder.add(merged(`arm${side}`, [sleeve, patch, cuff, glove]));
    torso.add(shoulder);
    return shoulder;
  };
  const shoulderL = arm(-1);
  const shoulderR = arm(1);

  // Legs exist only so a figure can walk (or hop). Seated at a desk they are
  // behind furniture and hidden.
  const legs = new THREE.Group();
  const leg = side => {
    const hip = new THREE.Group();
    hip.position.set(side * 0.2, 0, 0);
    const trouser = capsule(0.165, 0.6, suit);
    trouser.position.y = -0.42;
    const knee = cylinder(0.17, 0.17, 0.06, 14, trim);
    knee.position.y = -0.42;
    const boot = roundedSlab(0.3, 0.2, 0.42, '#7d8696', 0.07);
    boot.position.set(0, -0.86, 0.05);
    hip.add(merged(`leg${side}`, [trouser, knee, boot]));
    return hip;
  };
  const hipL = leg(-1);
  const hipR = leg(1);
  legs.add(hipL, hipR);
  legs.position.y = 1.55;
  legs.visible = false;
  group.add(legs);

  const head = new THREE.Group();
  head.position.y = 1.02;
  const helmet = new THREE.Mesh(geometry('astro-helmet', () => new THREE.SphereGeometry(0.5, 28, 20)), suit);
  helmet.castShadow = true;
  // The visor: a band of a slightly larger sphere across the front (+z).
  const visor = new THREE.Mesh(geometry('astro-visor', () => new THREE.SphereGeometry(
    0.505, 28, 14, Math.PI / 2 - Math.PI * 0.36, Math.PI * 0.72, Math.PI * 0.3, Math.PI * 0.36,
  )), visorMat);
  const ear = side => {
    const e = cylinder(0.1, 0.1, 0.08, 14, trim);
    e.rotation.z = Math.PI / 2;
    e.position.set(side * 0.5, 0, 0);
    return e;
  };
  head.add(merged('head', [helmet, ear(-1), ear(1)]));
  visor.castShadow = false;
  head.add(visor);
  torso.add(head);

  group.userData.joints = { torso, shoulderL, shoulderR, head, legs, hipL, hipR };
  group.userData.pose = 'work';
  group.userData.poseTargets = null;
  return group;
}

/**
 * A low-gravity hop instead of a stride: legs together, knees tucking a
 * little at the top of the arc and reaching for the floor on the way down,
 * arms floating out to the sides for balance.
 */
export function poseHop(person, f, dt) {
  const joints = person && person.userData && person.userData.joints;
  if (!joints) return;
  // `f` is how far through the current hop (0-1, motion.js createHopper).
  // Eased like poseWorker, so taking off or landing never snaps the limbs.
  const air = Math.sin(Math.PI * Math.max(0, Math.min(1, f)));
  const k = dt == null ? 1 : 1 - Math.exp(-Math.min(0.1, Math.max(0, dt)) * 14);
  joints.legs.visible = true;
  const ease = (obj, key, target) => { obj[key] = lerp(obj[key], target, k); };
  ease(joints.hipL.rotation, 'x', -0.15 - 0.35 * air);
  ease(joints.hipR.rotation, 'x', -0.15 - 0.35 * air);
  ease(joints.shoulderL.rotation, 'x', -0.25 - 0.2 * air);
  ease(joints.shoulderR.rotation, 'x', -0.25 - 0.2 * air);
  ease(joints.shoulderL.rotation, 'z', -(0.35 + 0.35 * air));
  ease(joints.shoulderR.rotation, 'z', 0.35 + 0.35 * air);
  ease(joints.head.rotation, 'x', 0);
  ease(joints.head.rotation, 'y', 0);
  ease(joints.torso.rotation, 'x', 0.12 - 0.08 * air);
  ease(joints.torso.position, 'y', 1.55);
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
    if (obj.userData && obj.userData.mergedGeometry && obj.geometry) obj.geometry.dispose();
    const owned = obj.userData && obj.userData.owned;
    if (owned) { owned.geometry.dispose(); owned.material.dispose(); }
  });
}

/** Drop the shared geometry/material caches. Only on full scene disposal. */
export function disposeSharedCaches() {
  _geometries.forEach(geo => { try { geo.dispose(); } catch (_err) { /* already gone */ } });
  _materials.forEach(mat => { try { mat.dispose(); } catch (_err) { /* already gone */ } });
  _iconTextures.forEach(tex => { try { tex.dispose(); } catch (_err) { /* already gone */ } });
  _geometries.clear();
  _materials.clear();
  _iconTextures.clear();
}

/* ---------- department scenery (the reference look) ---------- */
//
// Scenery only: none of it carries state, so it can never mislead anyone
// about what Hermes is doing. Every piece is a few shared-geometry meshes in
// the same rounded, toy-like style as the desks; nothing here casts a shadow
// (the desks and people already do, and a prop's shadow costs a shadow-pass
// draw every frame for no information).

/** What a department is about, from its name: picks its icon and its props. */
export function deptKind(label) {
  const text = String(label || '').toLowerCase();
  const rules = [
    ['research', /research|analys|insight|study/], ['coding', /cod|dev|engineer|software|tech|build/],
    ['documents', /doc|writ|content|paper|legal/], ['emails', /mail|inbox|message|outreach/],
    ['marketing', /market|brand|social|campaign|ads?\b/], ['sales', /sale|deal|crm|revenue|lead/],
    ['finance', /financ|account|budget|invoice|money|pay/], ['operations', /operat|ops|admin|process|it\b/],
    ['delivery', /deliver|ship|logist|fulfil|support/], ['floor', /the floor/], ['general', /general|misc|other/],
  ];
  const hit = rules.find(([, re]) => re.test(text));
  return hit ? hit[0] : 'general';
}

/**
 * A shared unlit material in `color`, brightened by `boost` past 1.0 so the
 * scene's bloom pass gives it a soft glow (tone mapping is off for it, or
 * ACES would pull it back under the bloom threshold). Cached like material().
 */
export function glowMaterial(color, boost, opts) {
  const options = opts || {};
  const key = `glow|${color}|${boost}|${options.opacity ?? 1}|${options.wireframe ? 1 : 0}|${options.additive ? 1 : 0}`;
  let mat = _materials.get(key);
  if (!mat) {
    mat = new THREE.MeshBasicMaterial({ color: new THREE.Color(color).multiplyScalar(boost), toneMapped: false });
    if (options.opacity != null && options.opacity < 1) { mat.transparent = true; mat.opacity = options.opacity; mat.depthWrite = false; }
    if (options.wireframe) mat.wireframe = true;
    if (options.additive) mat.blending = THREE.AdditiveBlending;
    _materials.set(key, mat);
  }
  return mat;
}

function hexOf(color, fallback) {
  return '#' + new THREE.Color(color || fallback).getHexString();
}

const ICON_PATHS = {
  // Each draws in a 100x100 box, stroked (round caps) in the department colour.
  general: (c) => { [[50, 30], [70, 50], [50, 70], [30, 50]].forEach(([x, y]) => { c.beginPath(); c.arc(x, y, 14, 0, Math.PI * 2); c.stroke(); }); c.beginPath(); c.arc(50, 50, 7, 0, Math.PI * 2); c.stroke(); },
  research: (c) => { c.beginPath(); c.arc(44, 44, 22, 0, Math.PI * 2); c.stroke(); c.beginPath(); c.moveTo(60, 60); c.lineTo(80, 80); c.stroke(); },
  coding: (c) => { c.beginPath(); c.moveTo(36, 30); c.lineTo(18, 50); c.lineTo(36, 70); c.moveTo(64, 30); c.lineTo(82, 50); c.lineTo(64, 70); c.moveTo(56, 24); c.lineTo(44, 76); c.stroke(); },
  documents: (c) => { c.beginPath(); c.moveTo(30, 16); c.lineTo(60, 16); c.lineTo(74, 30); c.lineTo(74, 84); c.lineTo(30, 84); c.closePath(); c.moveTo(60, 16); c.lineTo(60, 30); c.lineTo(74, 30); c.moveTo(40, 50); c.lineTo(64, 50); c.moveTo(40, 64); c.lineTo(58, 64); c.stroke(); },
  emails: (c) => { c.beginPath(); c.rect(16, 28, 68, 46); c.moveTo(16, 30); c.lineTo(50, 56); c.lineTo(84, 30); c.stroke(); },
  marketing: (c) => { c.beginPath(); c.moveTo(20, 42); c.lineTo(20, 60); c.lineTo(34, 60); c.lineTo(70, 78); c.lineTo(70, 24); c.lineTo(34, 42); c.closePath(); c.moveTo(34, 60); c.lineTo(40, 80); c.moveTo(80, 40); c.lineTo(88, 36); c.moveTo(80, 51); c.lineTo(90, 51); c.moveTo(80, 62); c.lineTo(88, 66); c.stroke(); },
  sales: (c) => { c.beginPath(); c.moveTo(16, 82); c.lineTo(84, 82); c.moveTo(24, 70); c.lineTo(44, 50); c.lineTo(58, 60); c.lineTo(82, 30); c.moveTo(68, 30); c.lineTo(82, 30); c.lineTo(82, 44); c.stroke(); },
  finance: (c) => { c.beginPath(); c.arc(50, 50, 32, 0, Math.PI * 2); c.moveTo(60, 36); c.bezierCurveTo(52, 28, 38, 32, 40, 42); c.bezierCurveTo(42, 52, 60, 48, 60, 58); c.bezierCurveTo(60, 70, 44, 70, 38, 62); c.moveTo(50, 24); c.lineTo(50, 76); c.stroke(); },
  operations: (c) => { c.beginPath(); for (let i = 0; i < 8; i += 1) { const a = i * Math.PI / 4; c.moveTo(50 + Math.cos(a) * 24, 50 + Math.sin(a) * 24); c.lineTo(50 + Math.cos(a) * 34, 50 + Math.sin(a) * 34); } c.stroke(); c.beginPath(); c.arc(50, 50, 22, 0, Math.PI * 2); c.stroke(); c.beginPath(); c.arc(50, 50, 9, 0, Math.PI * 2); c.stroke(); },
  delivery: (c) => { c.beginPath(); c.moveTo(50, 16); c.lineTo(82, 32); c.lineTo(82, 68); c.lineTo(50, 84); c.lineTo(18, 68); c.lineTo(18, 32); c.closePath(); c.moveTo(18, 32); c.lineTo(50, 48); c.lineTo(82, 32); c.moveTo(50, 48); c.lineTo(50, 84); c.stroke(); },
  floor: (c) => { c.beginPath(); c.arc(36, 36, 11, 0, Math.PI * 2); c.arc(66, 36, 11, 0, Math.PI * 2); c.stroke(); c.beginPath(); c.moveTo(16, 76); c.quadraticCurveTo(36, 50, 52, 76); c.moveTo(48, 76); c.quadraticCurveTo(66, 50, 86, 76); c.stroke(); },
};

/** A canvas texture of a department's icon, glowing in its colour on a dark rounded tile. */
function iconTexture(kind, color) {
  const key = `icon-tex|${kind}|${color}`;
  let tex = _iconTextures.get(key);
  if (tex) return tex;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 256;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, 256, 256);
  // Drawn once on a scratch canvas, then centred by its actual ink: the
  // icon paths sit at different heights in their own boxes, so some signs
  // showed their icon well below the middle of the wall.
  const scratch = document.createElement('canvas');
  scratch.width = scratch.height = 256;
  const sc = scratch.getContext('2d');
  sc.save();
  sc.translate(28, 28);
  sc.scale(2, 2);
  sc.strokeStyle = color;
  sc.lineWidth = 7;
  sc.lineCap = 'round';
  sc.lineJoin = 'round';
  (ICON_PATHS[kind] || ICON_PATHS.general)(sc);
  sc.restore();
  const ink = sc.getImageData(0, 0, 256, 256).data;
  let minX = 256, minY = 256, maxX = -1, maxY = -1;
  for (let y = 0; y < 256; y += 1) {
    for (let x = 0; x < 256; x += 1) {
      if (ink[(y * 256 + x) * 4 + 3] > 24) {
        if (x < minX) minX = x; if (x > maxX) maxX = x;
        if (y < minY) minY = y; if (y > maxY) maxY = y;
      }
    }
  }
  const dx = maxX >= 0 ? 128 - (minX + maxX) / 2 : 0;
  const dy = maxY >= 0 ? 128 - (minY + maxY) / 2 : 0;
  ctx.save();
  ctx.shadowColor = color;
  ctx.shadowBlur = 20;
  ctx.drawImage(scratch, dx, dy);
  ctx.restore();
  tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  _iconTextures.set(key, tex);
  return tex;
}
const _iconTextures = new Map();

/** A bookshelf: a dark frame, three shelves and rows of chunky coloured books. */
export function makeBookshelf(palette, width) {
  const w = width || 2.6;
  const group = new THREE.Group();
  const frame = roundedSlab(w, 0.12, 0.7, '#3a3346', 0.05);
  [0.06, 2.3].forEach(y => { const board = frame.clone(); board.position.y = y; group.add(board); });
  [-w / 2 + 0.06, w / 2 - 0.06].forEach(x => {
    const side = box(0.12, 2.36, 0.7, '#3a3346');
    side.position.set(x, 1.18, 0);
    side.castShadow = false;
    group.add(side);
  });
  const back = box(w, 2.3, 0.06, '#2a2433');
  back.position.set(0, 1.18, -0.32);
  back.castShadow = false;
  group.add(back);
  const BOOKS = ['#e05d5d', '#f2b84b', '#5fa8e8', '#7ac77a', '#b07ae0', '#ef8a5b', '#4fc7c0'];
  [0.12, 0.86, 1.6].forEach((y, shelf) => {
    if (shelf > 0) { const board = frame.clone(); board.position.y = y; group.add(board); }
    let x = -w / 2 + 0.2;
    let i = shelf * 3;
    while (x < w / 2 - 0.3) {
      const bw = 0.14 + ((i * 37) % 5) * 0.025;
      const bh = 0.5 + ((i * 53) % 4) * 0.06;
      const book = box(bw, bh, 0.5, BOOKS[i % BOOKS.length]);
      book.castShadow = false;
      book.position.set(x + bw / 2, y + 0.06 + bh / 2, 0.02);
      if (i % 7 === 3) book.rotation.z = 0.18;
      group.add(book);
      x += bw + 0.025;
      i += 1;
      if (i % 9 === 8) x += 0.3;  // a gap now and then, as on a real shelf
    }
  });
  group.traverse(o => { o.castShadow = false; });
  return group;
}

/** A clipped topiary: a pot and a chunky rounded green block (the reference's cube shrub). */
/**
 * A stepped topiary as in the reference: a square terracotta pot, a short
 * trunk and four green tiers, each smaller than the one below.
 */
export function makeTopiary(palette) {
  const group = new THREE.Group();
  const pot = squarePot(0.34, 0.27, 0.5, '#b9673c');
  pot.position.y = 0.25;
  group.add(pot);
  const rim = roundedSlab(0.74, 0.08, 0.74, '#a85a33', 0.04);
  rim.position.y = 0.5;
  group.add(rim);
  const trunk = box(0.14, 0.3, 0.14, '#6b4428');
  trunk.position.y = 0.68;
  group.add(trunk);
  const greens = ['#4ea535', '#5cb53c', '#6ac444', '#7fd352'];
  [0.98, 0.8, 0.62, 0.42].forEach((size, i) => {
    const tier = roundedSlab(size, 0.36, size, greens[i], 0.07);
    tier.position.y = 0.83 + i * 0.37 + 0.18;
    group.add(tier);
  });
  group.traverse(o => { o.castShadow = false; });
  return group;
}

/** A square pot that narrows toward the base (a four-sided cylinder). */
function squarePot(halfTop, halfBottom, height, color) {
  const mesh = new THREE.Mesh(
    geometry(`square-pot|${halfTop}|${halfBottom}|${height}`, () => {
      const g = new THREE.CylinderGeometry(halfTop * Math.SQRT2, halfBottom * Math.SQRT2, height, 4, 1);
      g.rotateY(Math.PI / 4);
      const flat = g.toNonIndexed();
      flat.computeVertexNormals();
      return flat;
    }),
    material(color, { rough: 0.75 }),
  );
  return mesh;
}

/**
 * A potted succulent as in the reference: a dark navy square pot and a
 * rosette of pointed leaves in three rings, lighter toward the middle.
 * (Kept under its old name; the scenery list calls it.)
 */
export function makePalm(palette) {
  const group = new THREE.Group();
  const pot = squarePot(0.36, 0.29, 0.62, '#2b3f63');
  pot.position.y = 0.31;
  group.add(pot);
  const rim = roundedSlab(0.78, 0.08, 0.78, '#36527d', 0.04);
  rim.position.y = 0.62;
  group.add(rim);
  const soil = box(0.6, 0.04, 0.6, '#3a2a1e');
  soil.position.y = 0.65;
  group.add(soil);
  const leafGeo = geometry('succulent-leaf', () => {
    const g = new THREE.ConeGeometry(0.24, 1, 4, 1);
    g.rotateY(Math.PI / 4);
    g.scale(1, 1, 0.42);
    g.translate(0, 0.5, 0);
    return g;
  });
  const rings = [
    { n: 9, tilt: 1.0, len: 0.85, color: '#3f9638', turn: 0 },
    { n: 7, tilt: 0.62, len: 0.85, color: '#55ad43', turn: 0.5 },
    { n: 5, tilt: 0.28, len: 0.7, color: '#72c652', turn: 0.25 },
  ];
  rings.forEach(ring => {
    for (let i = 0; i < ring.n; i += 1) {
      const leaf = new THREE.Mesh(leafGeo, material(ring.color, { rough: 0.7 }));
      leaf.position.y = 0.66;
      leaf.scale.set(1, ring.len, 1);
      leaf.rotation.set(ring.tilt, (i + ring.turn) * (Math.PI * 2 / ring.n), 0, 'YXZ');
      group.add(leaf);
    }
  });
  group.traverse(o => { o.castShadow = false; });
  return group;
}

/** A two-drawer filing cabinet. */
export function makeCabinet(palette, tint) {
  const group = new THREE.Group();
  const body = roundedSlab(0.9, 1.5, 0.8, '#3b4458', 0.08);
  body.position.y = 0.75;
  group.add(body);
  [0.45, 1.1].forEach(y => {
    const handle = box(0.35, 0.06, 0.06, tint || '#cbd5e1');
    handle.position.set(0, y, 0.42);
    group.add(handle);
  });
  group.traverse(o => { o.castShadow = false; });
  return group;
}

/** A server rack: a dark cabinet with rows of glowing status lights. */
export function makeServerRack(palette, tint) {
  const group = new THREE.Group();
  const body = roundedSlab(1.0, 2.4, 0.9, '#1d2333', 0.08);
  body.position.y = 1.2;
  group.add(body);
  const led = glowMaterial(hexOf(tint, '#38bdf8'), 1.7);
  for (let r = 0; r < 6; r += 1) {
    const strip = new THREE.Mesh(geometry('rack-led', () => new THREE.BoxGeometry(0.6, 0.05, 0.04)), led);
    strip.position.set(-0.1, 0.45 + r * 0.33, 0.47);
    group.add(strip);
  }
  group.traverse(o => { o.castShadow = false; });
  return group;
}

/** A standing board with a rising bar chart (sales) or a lit billboard (marketing). */
export function makeChartBoard(palette, tint, billboard) {
  const group = new THREE.Group();
  [-0.75, 0.75].forEach(x => { const leg = cylinder(0.05, 0.05, 1.3, 6, '#4a5266'); leg.position.set(x, 0.65, 0); group.add(leg); });
  const board = roundedPanel(1.9, 1.3, 0.1, billboard ? '#1b2033' : '#eef2f7', 0.1);
  board.position.y = 1.9;
  group.add(board);
  const glow = glowMaterial(hexOf(tint, '#f59e0b'), billboard ? 1.5 : 1.1);
  if (billboard) {
    const screen = new THREE.Mesh(geometry('billboard-screen', () => new THREE.PlaneGeometry(1.6, 1.0)), glow);
    screen.position.set(0, 1.9, 0.07);
    group.add(screen);
  } else {
    [0.35, 0.6, 0.5, 0.9].forEach((h, i) => {
      const bar = new THREE.Mesh(geometry(`chart-bar|${h}`, () => new THREE.BoxGeometry(0.26, h, 0.04)), glow);
      bar.position.set(-0.6 + i * 0.4, 1.4 + h / 2, 0.08);
      group.add(bar);
    });
  }
  group.traverse(o => { o.castShadow = false; });
  return group;
}

/** A stack of cardboard parcels. */
export function makeParcels() {
  const group = new THREE.Group();
  [[0, 0.35, 0, 0.9, 0.7, 0.8, 0], [0.15, 1.0, 0.05, 0.7, 0.6, 0.6, 0.3], [-0.55, 0.3, 0.6, 0.6, 0.6, 0.55, -0.2]].forEach(([x, y, z, w, h, d, ry]) => {
    const parcel = roundedSlab(w, h, d, '#c8955b', 0.05);
    parcel.position.set(x, y, z);
    parcel.rotation.y = ry;
    group.add(parcel);
    const tape = box(w + 0.02, 0.04, 0.12, '#e8d3a8');
    tape.position.set(x, y + h / 2, z);
    tape.rotation.y = ry;
    group.add(tape);
  });
  group.traverse(o => { o.castShadow = false; });
  return group;
}

/** A small office safe with a dial. */
export function makeSafe(palette, tint) {
  const group = new THREE.Group();
  const body = roundedSlab(1.0, 1.1, 0.9, '#4b5568', 0.1);
  body.position.y = 0.55;
  group.add(body);
  const dial = cylinder(0.16, 0.16, 0.08, 16, tint || '#fbbf24');
  dial.rotation.x = Math.PI / 2;
  dial.position.set(0.15, 0.6, 0.47);
  group.add(dial);
  group.traverse(o => { o.castShadow = false; });
  return group;
}

/** Wall-mounted mail cubbies: a grid of pigeonholes with a few letters in them. */
export function makeMailCubbies(palette, tint) {
  const group = new THREE.Group();
  // Pigeonholes on a low cabinet, so they stand on the deck (they used to
  // hang in mid-air above it).
  const base = roundedSlab(2.0, 0.85, 0.5, '#2a2433', 0.06);
  base.position.y = 0.425;
  group.add(base);
  const frame = roundedSlab(2.0, 1.5, 0.5, '#3a3346', 0.06);
  frame.position.y = 1.6;
  group.add(frame);
  for (let r = 0; r < 3; r += 1) {
    for (let c = 0; c < 4; c += 1) {
      const hole = box(0.38, 0.32, 0.06, '#1c1824');
      hole.position.set(-0.69 + c * 0.46, 1.17 + r * 0.43, 0.24);
      group.add(hole);
      if ((r * 4 + c) % 3 === 0) {
        const letter = box(0.3, 0.2, 0.03, (r + c) % 2 ? '#f8fafc' : (tint || '#86efac'));
        letter.position.set(-0.69 + c * 0.46, 1.17 + r * 0.43, 0.28);
        group.add(letter);
      }
    }
  }
  group.traverse(o => { o.castShadow = false; });
  return group;
}

/** A water cooler, for the open floor. */
export function makeWaterCooler() {
  const group = new THREE.Group();
  const stand = roundedSlab(0.7, 1.2, 0.7, '#e2e8f0', 0.1);
  stand.position.y = 0.6;
  group.add(stand);
  const bottle = new THREE.Mesh(geometry('cooler-bottle', () => new THREE.CylinderGeometry(0.3, 0.3, 0.8, 16)),
    material('#7cc7f2', { transparent: true, opacity: 0.75, rough: 0.2 }));
  bottle.position.y = 1.6;
  group.add(bottle);
  group.traverse(o => { o.castShadow = false; });
  return group;
}

/** A vending machine: a tall cabinet with a lit window of coloured cans. */
export function makeVendingMachine(tint) {
  const group = new THREE.Group();
  const body = roundedSlab(1.05, 2.3, 0.85, '#232a3a', 0.08);
  body.position.y = 1.15;
  group.add(body);
  const glass = new THREE.Mesh(geometry('vend-glass', () => new THREE.PlaneGeometry(0.62, 1.5)), glowMaterial('#9fd3ff', 0.55));
  glass.position.set(-0.13, 1.35, 0.43);
  group.add(glass);
  const cans = ['#ef4444', '#f59e0b', '#22c55e', '#3b82f6'];
  for (let r = 0; r < 4; r += 1) {
    for (let c = 0; c < 3; c += 1) {
      const can = cylinder(0.07, 0.07, 0.2, 10, cans[(r + c) % cans.length]);
      can.position.set(-0.32 + c * 0.19, 0.78 + r * 0.36, 0.45);
      group.add(can);
    }
  }
  const panel = box(0.18, 0.9, 0.04, '#11151f');
  panel.position.set(0.36, 1.45, 0.44);
  group.add(panel);
  const strip = box(0.9, 0.08, 0.04, glowMaterial(hexOf(tint, '#facc15'), 1.0));
  strip.position.set(0, 2.18, 0.44);
  group.add(strip);
  group.traverse(o => { o.castShadow = false; });
  return group;
}

/** A small lounge: a low two-seat sofa facing a round coffee table. */
export function makeLoungeSofa(tint) {
  const group = new THREE.Group();
  const fabric = mixColor('#3b4256', hexOf(tint, '#facc15'), 0.25);
  const seat = roundedSlab(2.4, 0.45, 0.9, fabric, 0.16);
  seat.position.set(0, 0.45, -0.45);
  group.add(seat);
  const back = roundedPanel(2.4, 0.75, 0.25, fabric, 0.14);
  back.position.set(0, 0.95, -0.82);
  group.add(back);
  [-1.1, 1.1].forEach(x => {
    const arm = roundedSlab(0.25, 0.7, 0.9, fabric, 0.1);
    arm.position.set(x, 0.55, -0.45);
    group.add(arm);
  });
  [-0.55, 0.55].forEach(x => {
    const cushion = roundedSlab(1.0, 0.16, 0.7, mixColor(fabric, '#ffffff', 0.12), 0.08);
    cushion.position.set(x, 0.75, -0.42);
    group.add(cushion);
  });
  const table = cylinder(0.42, 0.42, 0.08, 24, '#c9a27a');
  table.position.set(0, 0.5, 0.45);
  group.add(table);
  const stem = cylinder(0.06, 0.06, 0.45, 10, '#2e3547');
  stem.position.set(0, 0.24, 0.45);
  group.add(stem);
  const mug = cylinder(0.07, 0.06, 0.12, 10, '#f8fafc');
  mug.position.set(0.12, 0.6, 0.4);
  group.add(mug);
  group.traverse(o => { o.castShadow = false; });
  return group;
}

/** The one prop that says what a department does. */
function departmentProp(kind, palette, tint) {
  switch (kind) {
    case 'coding': case 'operations': return { make: () => makeServerRack(palette, tint), w: 1.0, d: 0.9 };
    case 'documents': return { make: () => makeCabinet(palette, tint), w: 0.9, d: 0.8 };
    case 'emails': return { make: () => makeMailCubbies(palette, tint), w: 2.0, d: 0.5 };
    case 'marketing': return { make: () => makeChartBoard(palette, tint, true), w: 1.9, d: 0.4 };
    case 'sales': return { make: () => makeChartBoard(palette, tint, false), w: 1.9, d: 0.4 };
    case 'finance': return { make: () => makeSafe(palette, tint), w: 1.0, d: 0.9 };
    case 'delivery': return { make: () => makeParcels(), w: 1.6, d: 1.4 };
    case 'floor': return { make: () => makeWaterCooler(), w: 0.7, d: 0.7 };
    default: return { make: () => makeCabinet(palette, tint), w: 0.9, d: 0.8 };
  }
}

/** A small potted cube shrub, for a corner a topiary is too big for. */
export function makeCubePlant() {
  const group = new THREE.Group();
  const pot = roundedSlab(0.66, 0.56, 0.66, '#b8693f', 0.05);
  pot.position.y = 0.28;
  group.add(pot);
  const bush = roundedSlab(0.74, 0.62, 0.74, '#62b83c', 0.12);
  bush.position.y = 0.56 + 0.31;
  group.add(bush);
  group.traverse(o => { o.castShadow = false; });
  return group;
}

/** A desktop printer on a low side table. */
export function makePrinterTable() {
  const group = new THREE.Group();
  const table = roundedSlab(1.2, 0.9, 0.8, '#4a5266', 0.06);
  table.position.y = 0.45;
  group.add(table);
  const printer = roundedSlab(0.9, 0.35, 0.65, '#e5e7eb', 0.08);
  printer.position.y = 1.08;
  group.add(printer);
  const tray = box(0.6, 0.03, 0.3, '#f8fafc');
  tray.position.set(0, 1.27, 0.12);
  group.add(tray);
  group.traverse(o => { o.castShadow = false; });
  return group;
}

/* ---- footprints: decorations never land on a desk, a walkway or a bridge ---- */

/** Corners of an oriented rectangle {x, z, w, d, rot} in 2D. */
function rectCorners(r) {
  const c = Math.cos(r.rot || 0), s = Math.sin(r.rot || 0);
  return [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b]) => {
    const lx = a * r.w / 2, lz = b * r.d / 2;
    // three.js rotation.y: x' = x cos + z sin, z' = -x sin + z cos
    return [r.x + lx * c + lz * s, r.z - lx * s + lz * c];
  });
}

/** Separating-axis test between two oriented rectangles. */
export function rectsOverlap(a, b) {
  const pa = rectCorners(a), pb = rectCorners(b);
  const axes = [];
  [pa, pb].forEach(poly => { for (let i = 0; i < 2; i += 1) {
    const [x1, z1] = poly[i], [x2, z2] = poly[i + 1];
    axes.push([-(z2 - z1), x2 - x1]);
  } });
  return axes.every(([ax, az]) => {
    const proj = poly => poly.map(([x, z]) => x * ax + z * az);
    const A = proj(pa), B = proj(pb);
    return Math.max(...A) > Math.min(...B) && Math.max(...B) > Math.min(...A);
  });
}

/** Tiny seeded random so a department always gets the same arrangement. */
function seeded(text) {
  let h = 2166136261;
  for (const ch of String(text)) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); }
  return () => { h ^= h << 13; h ^= h >>> 17; h ^= h << 5; return ((h >>> 0) % 10000) / 10000; };
}

/**
 * Low guardrails round the slab's edge, as in the reference: a dark kick
 * panel, frosted glass above it and a top rail with a thin glowing strip in
 * the department's colour, posts between runs. The same on every side and
 * at every angle; the bridge's entrance and the sign wall are left open.
 */
export function makeGuardRails(slabW, slabD, tint, openings, opts) {
  const options = opts || {};
  const group = new THREE.Group();
  const inset = RAIL_INSET;
  const w = slabW - inset * 2;
  const d = slabD - inset * 2;
  const radius = Math.max(0.3, Math.min(slabW, slabD) * 0.12 - inset);
  const hex = hexOf(tint, '#7dd3fc');
  const kick = material(options.kickColor || '#2b3245', { rough: 0.8 });
  const rail = material(options.railColor || '#3a4358', { rough: 0.6, metal: 0.3 });
  const glass = material(options.glassColor || '#cfe3ff', { rough: 0.15, transparent: true, opacity: options.glassOpacity ?? 0.16 });
  const glow = glowMaterial(hex, 1.05);
  const glassTop = options.glassTop ?? 0.9;
  const openingAt = (x, z) => (openings || []).find(o => Math.hypot(x - o.x, z - o.z) < o.r) || null;
  // The rail follows the rounded rectangle point by point (0.15 apart), so
  // its corners are true curves and the run is one piece from gap to gap.
  const shape = roundedRectShape(w, d, radius);
  const perimeter = 2 * (w + d) - (8 - 2 * Math.PI) * Math.min(radius, w / 2 - 0.05, d / 2 - 0.05);
  const count = Math.max(48, Math.round(perimeter / 0.15));
  const pts = shape.getSpacedPoints(count).slice(0, count).map(v => ({ x: v.x, z: -v.y }));
  const openBy = pts.map(pt => openingAt(pt.x, pt.z));
  const runs = [];
  if (!openBy.some(Boolean)) {
    runs.push({ points: pts, closed: true });
  } else {
    // Start just after a gap so no run wraps round the end of the array.
    // Each run remembers the openings at its two ends: a bridge gap gets a
    // marker post there, a sign wall (post: false) is what the rail meets.
    const start = openBy.findIndex(Boolean);
    let current = null;
    let before = null;
    for (let k = 1; k <= count; k += 1) {
      const i = (start + k) % count;
      if (openBy[i]) {
        if (current) { runs.push({ points: current, closed: false, before, after: openBy[i] }); current = null; }
        before = openBy[i];
        continue;
      }
      (current || (current = [])).push(pts[i]);
    }
    if (current) runs.push({ points: current, closed: false, before, after: openBy[start] });
  }
  const posts = [];
  runs.forEach(({ points, closed, before, after }) => {
    // A stub left between two bridges that land close together is clutter
    // (a scrap of rail with a post at each end): leave that stretch open.
    if (points.length < 2 || (!closed && points.length * 0.15 < 1.8)) return;
    const parts = [
      [kick, 0.06, 0, 0.34],
      [glass, 0.02, 0.34, glassTop],
      [glow, 0.075, 0.345, 0.38],
      [rail, 0.07, glassTop, glassTop + 0.08],
    ];
    if (options.topGlow) parts.push([glow, 0.035, glassTop + 0.08, glassTop + 0.11]);
    parts.forEach(([mat, half, y0, y1]) => {
      const mesh = new THREE.Mesh(ribbonGeometry(points, closed, half, y0, y1), mat);
      mesh.castShadow = false;
      group.add(mesh);
    });
    // Slim uprights every ~1.4 along the run.
    for (let i = 4; i < points.length - 4; i += 9) {
      const support = new THREE.Mesh(geometry(`rail-post|${glassTop}`, () => new THREE.BoxGeometry(0.12, glassTop + 0.08, 0.12)), rail);
      support.position.set(points[i].x, (glassTop + 0.08) / 2, points[i].z);
      support.castShadow = false;
      group.add(support);
    }
    if (!closed) {
      if (before && before.post !== false) posts.push(points[0]);
      if (after && after.post !== false) posts.push(points[points.length - 1]);
    }
  });
  // A marker post at each end of every run: the bridge's docking beacons.
  posts.forEach(pt => {
    const post = makeLampPost();
    post.position.set(pt.x, 0, pt.z);
    group.add(post);
  });
  group.userData.markerPosts = posts;
  return group;
}

/**
 * A rectangular profile (half-thickness `half`, from y0 to y1) swept along a
 * flat polyline: its two sides and top, and end caps when the run is open.
 */
function ribbonGeometry(points, closed, half, y0, y1) {
  const n = points.length;
  const normals = points.map((p, i) => {
    const a = points[closed ? (i - 1 + n) % n : Math.max(0, i - 1)];
    const b = points[closed ? (i + 1) % n : Math.min(n - 1, i + 1)];
    const l = Math.hypot(b.x - a.x, b.z - a.z) || 1;
    return { x: -(b.z - a.z) / l, z: (b.x - a.x) / l };
  });
  const pos = [];
  const nor = [];
  const idx = [];
  const quadStrip = (verts, faceNormals) => {
    // verts: per point [v0, v1]; joined point to point.
    const base = pos.length / 3;
    verts.forEach(([v0, v1], i) => {
      pos.push(v0.x, v0.y, v0.z, v1.x, v1.y, v1.z);
      const fn = faceNormals[i];
      nor.push(fn.x, fn.y, fn.z, fn.x, fn.y, fn.z);
    });
    const segs = closed ? n : n - 1;
    for (let i = 0; i < segs; i += 1) {
      const j = (i + 1) % n;
      const a = base + i * 2, b = base + j * 2;
      idx.push(a, b, a + 1, b, b + 1, a + 1);
    }
  };
  [1, -1].forEach(side => {
    quadStrip(points.map((p, i) => {
      const q = { x: p.x + normals[i].x * half * side, z: p.z + normals[i].z * half * side };
      return side > 0 ? [{ x: q.x, y: y0, z: q.z }, { x: q.x, y: y1, z: q.z }] : [{ x: q.x, y: y1, z: q.z }, { x: q.x, y: y0, z: q.z }];
    }), normals.map(m => ({ x: m.x * side, y: 0, z: m.z * side })));
  });
  quadStrip(points.map((p, i) => [
    { x: p.x + normals[i].x * half, y: y1, z: p.z + normals[i].z * half },
    { x: p.x - normals[i].x * half, y: y1, z: p.z - normals[i].z * half },
  ]), normals.map(() => ({ x: 0, y: 1, z: 0 })));
  if (!closed) {
    [[0, 1], [n - 1, n - 2]].forEach(([i, k]) => {
      const p = points[i], m = normals[i];
      const tx = p.x - points[k].x, tz = p.z - points[k].z;
      const l = Math.hypot(tx, tz) || 1;
      const base = pos.length / 3;
      [[-1, y0], [1, y0], [1, y1], [-1, y1]].forEach(([sd, y]) => {
        pos.push(p.x + m.x * half * sd, y, p.z + m.z * half * sd);
        nor.push(tx / l, 0, tz / l);
      });
      // Wound to face outward: the start cap and the end cap face opposite ways.
      if (i === 0) idx.push(base, base + 1, base + 2, base, base + 2, base + 3);
      else idx.push(base, base + 2, base + 1, base, base + 3, base + 2);
    });
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  g.setIndex(idx);
  return g;
}

/** How far in from a slab's edge the guardrails (and marker posts) stand. */
export const RAIL_INSET = 0.32;

/**
 * Half the width of the gap a bridge leaves in a platform's rail, measured
 * along the edge: the deck's half-width stretched by how obliquely it meets
 * the edge, plus room for a marker post either side.
 */
export function bridgeGapHalfWidth(dirX, dirZ) {
  const len = Math.hypot(dirX, dirZ) || 1;
  const along = Math.max(Math.abs(dirX), Math.abs(dirZ)) / len;
  return (BRIDGE_DECK_WIDTH / 2) / Math.max(0.5, along) + 0.65;
}

/**
 * The department's sign: a short freestanding wall at the slab's edge with
 * its icon glowing on the face the camera sees (the reference's display wall).
 */
export function makeSignWall(kind, tint) {
  const group = new THREE.Group();
  const wall = roundedPanel(2.4, 2.3, 0.45, '#1b2234', 0.18);
  wall.position.y = 1.15;
  group.add(wall);
  const trim = new THREE.Mesh(geometry('sign-trim', () => new THREE.BoxGeometry(2.3, 0.06, 0.49)), glowMaterial(hexOf(tint, '#7dd3fc'), 1.05));
  trim.position.y = 2.31;
  group.add(trim);
  const glowColor = hexOf(tint, '#7dd3fc');
  const matKey = `icon-mat|${kind}|${glowColor}`;
  let iconMat = _materials.get(matKey);
  if (!iconMat) {
    iconMat = new THREE.MeshBasicMaterial({ map: iconTexture(kind, glowColor), transparent: true, depthWrite: false, toneMapped: false });
    iconMat.color.setScalar(1.25);
    _materials.set(matKey, iconMat);
  }
  const icon = new THREE.Mesh(geometry('sign-icon', () => new THREE.PlaneGeometry(1.7, 1.7)), iconMat);
  icon.position.set(0, 1.15, 0.24);
  icon.renderOrder = 4;
  group.add(icon);
  group.traverse(o => { o.castShadow = false; });
  return group;
}

/**
 * A department's scenery on its slab (local coordinates; the top at y=0.6):
 * guardrails round the edge, its sign wall on an edge the camera sees, and
 * a scattered set of decorations -- bookshelf, plants, the department's own
 * prop, a printer -- each placed where it touches no desk, no worker's
 * walk-in path and no bridge entrance (`opts.blocked`, oriented rectangles;
 * `opts.entry`, the bridge's landing point). Placement is seeded by the
 * department, so it stays put between visits but differs between pods.
 */
export function makePodScenery(kind, slabW, slabD, palette, tint, opts) {
  const options = opts || {};
  const group = new THREE.Group();
  const top = 0.6;
  const rand = seeded(`${kind}|${options.seed || ''}`);
  const entry = options.entry || null;
  const blocked = (options.blocked || []).slice();
  const openings = [];
  if (entry) {
    openings.push({ x: entry.x, z: entry.z, r: bridgeGapHalfWidth(entry.x, entry.z) });
    blocked.push({ x: entry.x, z: entry.z, w: 5.4, d: 5.4, rot: 0 });
  }
  const placed = [];   // footprints with a little spacing, so pieces don't touch
  const footprints = []; // what each piece actually covers
  // Inside the guardrails (they stand 0.25-0.4 in from the edge).
  const EDGE = 0.62;
  const fits = r => {
    const pts = rectCorners(r);
    const inside = pts.every(([x, z]) => Math.abs(x) <= slabW / 2 - EDGE + 1e-6 && Math.abs(z) <= slabD / 2 - EDGE + 1e-6);
    return inside && !blocked.some(b => rectsOverlap(r, b)) && !placed.some(b => rectsOverlap(r, b));
  };
  // Points along the inside of each edge, each with the inward direction
  // and the rotation that turns a piece's front (+z) to face the middle.
  const edges = [
    { ax: 'x', at: -slabD / 2, nx: 0, nz: 1, rot: 0, len: slabW, far: true },          // back (-z)
    { ax: 'z', at: -slabW / 2, nx: 1, nz: 0, rot: Math.PI / 2, len: slabD, far: true }, // left (-x)
    { ax: 'x', at: slabD / 2, nx: 0, nz: -1, rot: Math.PI, len: slabW, far: false },   // front (+z)
    { ax: 'z', at: slabW / 2, nx: -1, nz: 0, rot: -Math.PI / 2, len: slabD, far: false }, // right (+x)
  ];
  const spotsFor = (edge, steps) => {
    const out = [];
    for (let i = 0; i <= steps; i += 1) {
      const t = (-0.5 + i / steps) * (edge.len - 2.2);
      out.push({ edge, t });
    }
    return out;
  };
  const rectAt = (spot, w, d) => {
    const { edge, t } = spot;
    const inward = EDGE + d / 2 + 0.02;
    const x = edge.ax === 'x' ? t : edge.at + edge.nx * inward;
    const z = edge.ax === 'x' ? edge.at + edge.nz * inward : t;
    return { x, z, w, d, rot: edge.rot };
  };

  // Sign wall: standing in the rail line itself on one of the two edges the
  // camera sees (+x, +z), as far from the bridge as it can be, with the rail
  // ending into its sides. It stays on the straight part of the edge, clear
  // of the rounded corners.
  const slabRadius = Math.min(slabW, slabD) * 0.12;
  const SIGN_W = 2.4;
  const signSpots = [];
  [edges[2], edges[3]].forEach(edge => {
    const room = edge.len / 2 - slabRadius - SIGN_W / 2 - 0.15;
    for (let i = 0; i <= 6 && room > 0; i += 1) {
      const t = (-1 + (2 * i) / 6) * room;
      const x = edge.ax === 'x' ? t : edge.at + edge.nx * RAIL_INSET;
      const z = edge.ax === 'x' ? edge.at + edge.nz * RAIL_INSET : t;
      signSpots.push({ x, z, w: SIGN_W, d: 0.45, rot: edge.rot });
    }
  });
  if (entry) signSpots.sort((a, b) => Math.hypot(b.x - entry.x, b.z - entry.z) - Math.hypot(a.x - entry.x, a.z - entry.z));
  else signSpots.sort((a, b) => Math.abs(a.x) + Math.abs(a.z) - Math.abs(b.x) - Math.abs(b.z));
  const clearOfBridge = r => !entry || Math.hypot(r.x - entry.x, r.z - entry.z) > bridgeGapHalfWidth(entry.x, entry.z) + SIGN_W / 2 + 0.6;
  const sign = signSpots.find(r => clearOfBridge(r) && !blocked.some(b => rectsOverlap(r, b)));
  if (sign) {
    const wall = makeSignWall(kind, tint);
    wall.position.set(sign.x, top, sign.z);
    // The sign faces outward, toward the camera.
    wall.rotation.y = sign.rot + Math.PI;
    group.add(wall);
    placed.push({ ...sign, w: sign.w + 0.4, d: sign.d + 0.8 });
    footprints.push(sign);
    // The rail stops at the wall's two ends.
    openings.push({ x: sign.x, z: sign.z, r: SIGN_W / 2 - 0.05, post: false });
  }
  if (!options.noRails) {
    const rails = makeGuardRails(slabW, slabD, tint, openings);
    rails.position.y = top;
    group.add(rails);
    rails.userData.markerPosts.forEach(pt => placed.push({ x: pt.x, z: pt.z, w: 0.9, d: 0.9, rot: 0 }));
  }

  // Decorations, biggest first, each tried along the inside of the edges in
  // a seeded order (tall pieces against the far edges first, where they hide
  // nothing); one that fits nowhere is left out rather than clipped.
  const prop = departmentProp(kind, palette, tint);
  const items = options.open
    // The Floor (open plan): a lounge, a vending machine, a server rack, a
    // bookshelf, water coolers and plenty of plants round its edge.
    ? [{ make: () => makeLoungeSofa(tint), w: 2.6, d: 1.9, tall: true },
       { make: () => makeVendingMachine(tint), w: 1.1, d: 0.9, tall: true },
       { make: () => makeBookshelf(palette, 2.4), w: 2.4, d: 0.7, tall: true },
       { make: () => makeServerRack(palette, tint), w: 1.0, d: 0.9, tall: true },
       { make: () => makeTopiary(palette), w: 1.2, d: 1.2 }, { make: () => makePalm(palette), w: 1.3, d: 1.3 },
       { make: () => makeWaterCooler(), w: 0.7, d: 0.7 }, { make: () => makeCubePlant(), w: 0.8, d: 0.8 },
       { make: () => makeTopiary(palette), w: 1.2, d: 1.2 }, { make: () => makePalm(palette), w: 1.3, d: 1.3 },
       { make: () => makePrinterTable(), w: 1.2, d: 0.8 }, { make: () => makeCubePlant(), w: 0.8, d: 0.8 },
       { make: () => makeWaterCooler(), w: 0.7, d: 0.7 }, { make: () => makePalm(palette), w: 1.3, d: 1.3 }]
    : [{ make: () => makeBookshelf(palette, 2.4), w: 2.4, d: 0.7, tall: true }, { ...prop, tall: true },
       { make: () => makeTopiary(palette), w: 1.2, d: 1.2 }, { make: () => makePalm(palette), w: 1.3, d: 1.3 },
       { make: () => makeCubePlant(), w: 0.8, d: 0.8 },
       rand() < 0.5 ? { make: () => makePrinterTable(), w: 1.2, d: 0.8 } : { make: () => makeCabinet(palette, tint), w: 0.9, d: 0.8 }];
  const all = edges.flatMap(edge => spotsFor(edge, 10));
  for (let i = all.length - 1; i > 0; i -= 1) { const j = Math.floor(rand() * (i + 1)); [all[i], all[j]] = [all[j], all[i]]; }
  items.forEach(item => {
    const order = item.tall ? all.filter(sp => sp.edge.far).concat(all.filter(sp => !sp.edge.far)) : all;
    for (const sp of order) {
      const r = rectAt(sp, item.w, item.d);
      if (!fits(r)) continue;
      const mesh = item.make();
      mesh.position.set(r.x, top, r.z);
      mesh.rotation.y = r.rot;
      group.add(mesh);
      placed.push({ ...r, w: r.w + 0.35, d: r.d + 0.35 });
      footprints.push(r);
      break;
    }
  });
  group.userData.scenery = true;
  group.userData.placed = footprints;
  // The sign's glowing icon is textured, so it stays its own mesh.
  return mergeStatic(group, `scenery|${kind}|${slabW}|${slabD}|${hexOf(tint, '#7dd3fc')}|${palette.podTop}|${options.open ? 1 : 0}|${options.key || ''}`);
}

/**
 * A neon marker post (the reference's docking beacon): a small dark
 * rounded column with a vertical warm-white light core showing through a
 * slot on every face, on a footing with a slim metal cap. Only the core
 * glows -- no halo or light pool round it. Boxes and two
 * materials, so a pod's posts merge into its scenery.
 */
export function makeLampPost(height) {
  const h = height || 1.3;
  const W = 0.46;
  const group = new THREE.Group();
  const frame = material('#262e40', { rough: 0.5, metal: 0.35 });
  const trim = material('#4a5570', { rough: 0.4, metal: 0.5 });
  const foot = roundedPlatform(W + 0.14, W + 0.14, 0.12, null, { radius: 0.1, bevel: 0.03, bevelSegments: 2, material: frame });
  foot.position.y = 0.06;
  group.add(foot);
  const body = roundedPlatform(W, W, h - 0.2, null, { radius: 0.1, bevel: 0.03, bevelSegments: 2, material: frame });
  body.position.y = 0.12 + (h - 0.2) / 2;
  group.add(body);
  const cap = roundedPlatform(W + 0.06, W + 0.06, 0.08, null, { radius: 0.11, bevel: 0.02, bevelSegments: 2, material: trim });
  cap.position.y = h - 0.04;
  group.add(cap);
  const coreH = h - 0.5;
  // Only the bar itself glows: an unlit, bright core kept under the bloom
  // threshold (bloom works on screen pixels, so a thin core lost its glow
  // zoomed out and smeared over the whole post zoomed in), with no halo.
  const core = glowMaterial('#fff0d4', 1.0);
  // The body's bevel stands 0.03 proud of W, so the core reaches past it.
  [[W + 0.09, 0.14], [0.14, W + 0.09]].forEach(([cw, cd]) => {
    const c = roundedPlatform(cw, cd, coreH, null, { radius: 0.06, bevel: 0.001, bevelSegments: 1, material: core });
    c.position.y = 0.12 + (h - 0.2) / 2 + 0.02;
    group.add(c);
  });
  group.traverse(o => { o.castShadow = false; o.receiveShadow = false; });
  return group;
}

/**
 * The conductor hub's set: a wide dark plinth with a glowing ring round its
 * top, a big glass globe in a glowing cup with electrons orbiting it, a
 * curved desk at each corner facing out, and marker posts at the corners
 * and either side of every bridge landing.
 *
 * `opts.bridges` is the angle (atan2(x, z)) of each bridge leaving the hub;
 * a desk whose corner a bridge comes too close to slides along the edge
 * away from it. The ring between plinth and desks stays clear for the
 * conductor.
 */
export function makeHubCentrepiece(slab, tint, opts) {
  const options = opts || {};
  const bridges = options.bridges || [];
  const group = new THREE.Group();
  const hex = hexOf(tint, '#4f8cff');
  const top = 0.6;
  // The plinth: a wide dark drum, a glowing ring round its top edge, and a
  // raised cup with its own ring that the globe sits in.
  const plinthH = 1.15;
  const plinth = new THREE.Mesh(geometry('hub-plinth', () => new THREE.CylinderGeometry(2.55, 2.7, plinthH, 64)), material('#2a3550', { rough: 0.45, metal: 0.3 }));
  plinth.position.y = top + plinthH / 2;
  group.add(plinth);
  const lip = new THREE.Mesh(geometry('hub-lip', () => new THREE.TorusGeometry(2.42, 0.07, 10, 96)), glowMaterial(hex, 1.5));
  lip.rotation.x = Math.PI / 2;
  lip.position.y = top + plinthH + 0.02;
  group.add(lip);
  const cupH = 0.3;
  const cup = new THREE.Mesh(geometry('hub-cup-base', () => new THREE.CylinderGeometry(1.35, 1.5, cupH, 64)), material('#11172a', { rough: 0.35, metal: 0.5 }));
  cup.position.y = top + plinthH + cupH / 2;
  group.add(cup);
  const cupRing = new THREE.Mesh(geometry('hub-cup-ring', () => new THREE.TorusGeometry(1.32, 0.06, 10, 80)), glowMaterial(hex, 1.7));
  cupRing.rotation.x = Math.PI / 2;
  cupRing.position.y = top + plinthH + cupH + 0.01;
  group.add(cupRing);
  // The globe: glass, clear in the middle and bright at the edge (a fresnel
  // shader), with a soft highlight and a glowing nucleus.
  const globeR = 2.2;
  const globeY = top + plinthH + cupH + globeR - 0.35;
  const globe = new THREE.Mesh(geometry('hub-globe3', () => new THREE.SphereGeometry(globeR, 64, 40)), globeMaterial(hex));
  globe.position.y = globeY;
  globe.renderOrder = 2;
  globe.userData.noMerge = true;
  group.add(globe);
  const core = new THREE.Mesh(geometry('hub-core', () => new THREE.SphereGeometry(globeR * 0.55, 32, 20)), glowMaterial(hex, 0.6, { opacity: 0.35, additive: true }));
  core.position.y = globeY - 0.25;
  core.userData.noMerge = true;
  group.add(core);
  const nucleus = new THREE.Mesh(geometry('hub-nucleus', () => new THREE.SphereGeometry(0.42, 32, 20)), glowMaterial('#8fc4ff', 1.15));
  nucleus.position.y = globeY;
  nucleus.userData.noMerge = true;
  group.add(nucleus);
  // Electrons: three tilted orbits round the globe, each a faint ring with
  // a bright electron running along it (animated by scene.js). The orbits
  // stay above the plinth and inside the conductor's walking ring.
  const orbits = [];
  const orbitR = 2.75;
  const ringMat = glowMaterial('#8cc8ff', 1.0, { opacity: 0.45, additive: true });
  const electronMat = glowMaterial('#d6ecff', 2.4);
  [0, 1, 2].forEach(i => {
    const orbit = new THREE.Group();
    orbit.position.y = globeY;
    orbit.rotation.set(Math.PI / 2 - 0.55, (i * Math.PI * 2) / 3, 0, 'YXZ');
    const ring = new THREE.Mesh(geometry('hub-orbit', () => new THREE.TorusGeometry(orbitR, 0.022, 6, 128)), ringMat);
    ring.userData.noMerge = true;
    orbit.add(ring);
    const electron = new THREE.Mesh(geometry('hub-electron', () => new THREE.SphereGeometry(0.13, 16, 12)), electronMat);
    electron.userData.noMerge = true;
    orbit.add(electron);
    orbits.push({ orbit, electron, radius: orbitR, angle: i * 2.1, speed: 1.1 + i * 0.25 });
    group.add(orbit);
  });
  // Guard rails round the deck: taller blue-tinted glass with a glowing cap,
  // open where each bridge lands (marker posts either side of each opening).
  const halfSlab = slab / 2;
  const openings = bridges.map(b => {
    const dx = Math.sin(b), dz = Math.cos(b);
    const t = halfSlab / Math.max(Math.abs(dx), Math.abs(dz));
    return { x: dx * t, z: dz * t, r: bridgeGapHalfWidth(dx, dz) };
  });
  const rails = makeGuardRails(slab, slab, hex, openings, {
    topGlow: true, glassTop: 1.05, glassColor: '#9cc4ff', glassOpacity: 0.2, kickColor: '#1c2436', railColor: '#2f3a55',
  });
  rails.position.y = top;
  group.add(rails);
  // Curved desks: one per corner, curving outward, the operator's gaming
  // chair on the inner side so desk and operator face out over the floor.
  // A desk a bridge comes near slides along the edge away from it, and
  // in toward the plinth if it would otherwise reach the rail.
  const half = slab / 2;
  const clear = 0.5; // radians a desk keeps from a bridge (and its posts)
  const deskScale = 1.3;
  const chairs = [];
  [0.25, 0.75, 1.25, 1.75].forEach(turn => {
    let a = turn * Math.PI;
    bridges.forEach(b => {
      const diff = Math.atan2(Math.sin(a - b), Math.cos(a - b));
      if (Math.abs(diff) < clear) a = b + Math.sign(diff || 1) * clear;
    });
    const reach = r => {
      let worst = 0;
      for (let k = -6; k <= 6; k += 1) {
        const phi = (k / 6) * DESK_HALF_SPAN;
        // Local (sin phi * R, -cos phi * R), local -z pointing outward.
        const lx = Math.sin(phi) * 2.15 * deskScale;
        const lout = Math.cos(phi) * 2.15 * deskScale;
        const x = Math.sin(a) * (r + lout) + Math.cos(a) * lx;
        const z = Math.cos(a) * (r + lout) - Math.sin(a) * lx;
        worst = Math.max(worst, Math.abs(x), Math.abs(z));
      }
      return worst;
    };
    // Nearest the desk's outer edge comes to a bridge's marker post.
    const posts = rails.userData.markerPosts;
    const postGap = r => {
      let nearest = Infinity;
      for (let k = -6; k <= 6; k += 1) {
        const phi = (k / 6) * DESK_HALF_SPAN;
        const lx = Math.sin(phi) * 2.15 * deskScale;
        const lout = Math.cos(phi) * 2.15 * deskScale;
        const x = Math.sin(a) * (r + lout) + Math.cos(a) * lx;
        const z = Math.cos(a) * (r + lout) - Math.sin(a) * lx;
        posts.forEach(pt => { nearest = Math.min(nearest, Math.hypot(pt.x - x, pt.z - z)); });
      }
      return nearest;
    };
    let r = 5.9;
    while (r > 4.5 && (reach(r) > half - 1.15 || postGap(r) < 1.1)) r -= 0.1;
    const desk = makeCurvedDesk(hex);
    desk.position.set(Math.sin(a) * r, top, Math.cos(a) * r);
    desk.rotation.y = a + Math.PI;
    desk.scale.setScalar(deskScale);
    group.add(desk);
    const seatR = r - 0.15 * deskScale;
    chairs.push({ x: Math.sin(a) * seatR, z: Math.cos(a) * seatR, facing: a });
  });
  group.traverse(o => { o.castShadow = false; });
  const merged = mergeStatic(group, `hub5|${slab}|${hex}|${bridges.map(b => b.toFixed(2)).join(',')}`);
  merged.userData.orbits = orbits;
  merged.userData.core = core;
  merged.userData.nucleus = nucleus;
  merged.userData.markerPosts = rails.userData.markerPosts;
  merged.userData.chairs = chairs;
  return merged;
}

const DESK_HALF_SPAN = Math.PI / 3;

/**
 * A curved operator desk with rounded ends: an arc of desk in front of a
 * dark gaming chair, three monitors on the curve facing the chair, and a
 * glowing trim along the operator's edge. The chair is at the local origin
 * and the desk curves round it toward -z.
 */
function makeCurvedDesk(hex) {
  const group = new THREE.Group();
  const span = DESK_HALF_SPAN;
  const deskTop = arcSlab(1.3, 2.1, span, 0.1, material('#3b465c', { rough: 0.45, metal: 0.25 }));
  deskTop.position.y = 0.92;
  group.add(deskTop);
  const body = arcSlab(1.5, 1.95, span * 0.94, 0.88, material('#232b3d', { rough: 0.6, metal: 0.2 }));
  body.position.y = 0.04;
  group.add(body);
  const trim = arcSlab(1.27, 1.35, span * 0.97, 0.05, glowMaterial(hex, 1.1));
  trim.position.y = 0.99;
  group.add(trim);
  let screenMat = _materials.get(`hub-ui|${hex}`);
  if (!screenMat) {
    screenMat = new THREE.MeshBasicMaterial({ map: hubScreenTexture(hex), toneMapped: false });
    screenMat.userData.mergeable = true;
    _materials.set(`hub-ui|${hex}`, screenMat);
  }
  [-0.5, 0, 0.5].forEach(theta => {
    const mon = new THREE.Group();
    mon.position.set(Math.sin(theta) * 1.82, 0, -Math.cos(theta) * 1.82);
    mon.rotation.y = -theta;
    const bezel = roundedPanel(1.0, 0.66, 0.07, '#0f1420', 0.05);
    bezel.position.y = 1.55;
    mon.add(bezel);
    const glass = new THREE.Mesh(geometry('hub-screen3', () => new THREE.PlaneGeometry(0.9, 0.56)), screenMat);
    glass.position.set(0, 1.55, 0.04);
    mon.add(glass);
    const stand = box(0.09, 0.4, 0.09, '#0f1420');
    stand.position.set(0, 1.2, -0.04);
    mon.add(stand);
    group.add(mon);
  });
  // The chair faces the desk (-z); its back is toward +z, the plinth.
  // Scaled so that, inside a desk drawn at 1.3x, it is a full-size chair a
  // figure can sit in.
  const chair = makeGamingChair(hex);
  chair.scale.setScalar(1 / 1.3);
  chair.position.set(0, 0, 0.15);
  group.add(chair);
  return group;
}

/**
 * A dark racing-style gaming chair, smaller than an office chair: a
 * five-spoke base, a seat with accent side bolsters, and a one-piece
 * backrest cut to the racing silhouette (flared shoulders, narrow neck, a
 * rounded head section) with accent stripes, a headrest and a lumbar
 * cushion. Like makeChair, the occupant faces -z.
 */
export function makeGamingChair(accent) {
  const group = new THREE.Group();
  const frame = '#101318';
  const shell = '#171a21';
  const pad = '#232833';
  const tone = hexOf(accent, '#4f8cff');
  const accentMat = material('#1d3566', { rough: 0.55, emissive: tone, ei: 0.25 });
  for (let i = 0; i < 5; i += 1) {
    const a = i * (Math.PI * 2 / 5);
    const spoke = box(0.1, 0.07, 0.62, frame);
    spoke.position.set(Math.sin(a) * 0.3, 0.14, Math.cos(a) * 0.3);
    spoke.rotation.y = a;
    group.add(spoke);
    const castor = cylinder(0.07, 0.07, 0.08, 10, frame);
    castor.rotation.z = Math.PI / 2;
    castor.position.set(Math.sin(a) * 0.58, 0.07, Math.cos(a) * 0.58);
    group.add(castor);
  }
  const lift = cylinder(0.065, 0.09, 0.72, 14, '#30353f');
  lift.position.y = 0.5;
  group.add(lift);
  const seat = roundedSlab(1.0, 0.2, 0.98, pad, 0.18);
  seat.position.y = 0.96;
  group.add(seat);
  [-0.47, 0.47].forEach(x => {
    const bolster = new THREE.Mesh(geometry('gchair-bolster', () => {
      const g = new THREE.CapsuleGeometry(0.09, 0.8, 4, 10);
      g.rotateX(Math.PI / 2);
      return g;
    }), accentMat);
    bolster.position.set(x, 1.1, -0.02);
    group.add(bolster);
  });
  const back = new THREE.Group();
  back.position.set(0, 1.04, 0.46);
  back.rotation.x = 0.12; // reclined a little, top toward +z
  const shellMesh = new THREE.Mesh(geometry('gchair-back', () => {
    const sh = new THREE.Shape();
    sh.moveTo(-0.44, 0);
    sh.lineTo(0.44, 0);
    sh.quadraticCurveTo(0.56, 0.5, 0.54, 1.0);   // flared shoulder
    sh.quadraticCurveTo(0.5, 1.22, 0.33, 1.3);   // into the neck
    sh.lineTo(0.35, 1.58);
    sh.quadraticCurveTo(0.35, 1.78, 0, 1.8);      // rounded head
    sh.quadraticCurveTo(-0.35, 1.78, -0.35, 1.58);
    sh.lineTo(-0.33, 1.3);
    sh.quadraticCurveTo(-0.5, 1.22, -0.54, 1.0);
    sh.quadraticCurveTo(-0.56, 0.5, -0.44, 0);
    const g = new THREE.ExtrudeGeometry(sh, { depth: 0.16, bevelEnabled: true, bevelThickness: 0.05, bevelSize: 0.05, bevelSegments: 3, curveSegments: 16 });
    return g;
  }), material(shell, { rough: 0.7 }));
  back.add(shellMesh);
  // Front face is at z = -0.05 (the bevel); the cushions sit just proud of it.
  [-0.27, 0.27].forEach(x => {
    const stripe = new THREE.Mesh(geometry('gchair-stripe', () => new THREE.BoxGeometry(0.08, 1.05, 0.03)), accentMat);
    stripe.position.set(x, 0.62, -0.07);
    back.add(stripe);
  });
  // The same stripes on the back of the shell (the side the camera mostly
  // sees on the hub), which is at z = 0.21.
  [-0.27, 0.27].forEach(x => {
    const stripe = new THREE.Mesh(geometry('gchair-stripe', () => new THREE.BoxGeometry(0.08, 1.05, 0.03)), accentMat);
    stripe.position.set(x, 0.62, 0.23);
    back.add(stripe);
  });
  const head = roundedPanel(0.4, 0.2, 0.08, pad, 0.08);
  head.position.set(0, 1.48, -0.1);
  back.add(head);
  const lumbar = roundedPanel(0.56, 0.2, 0.09, pad, 0.08);
  lumbar.position.set(0, 0.32, -0.1);
  back.add(lumbar);
  group.add(back);
  [-0.6, 0.6].forEach(x => {
    const post = box(0.08, 0.34, 0.08, frame);
    post.position.set(x, 1.15, 0.12);
    group.add(post);
    const arm = roundedSlab(0.14, 0.08, 0.62, frame, 0.04);
    arm.position.set(x, 1.34, 0.02);
    group.add(arm);
  });
  group.traverse(o => { o.castShadow = false; });
  return mergeStatic(group, `gaming-chair2|${tone}`);
}

/**
 * A flat ring segment between radii r0 and r1, centred on -z and spanning
 * ±halfSpan, `height` tall from y=0 up, its two ends rounded.
 */
function arcSlab(r0, r1, halfSpan, height, mat) {
  const geo = geometry(`arc-slab2|${r0}|${r1}|${halfSpan.toFixed(3)}|${height}`, () => {
    // In shape space (x, y) maps to world (x, -y) once stood up, so the
    // curve centred on world -z is centred on shape +y.
    const a0 = Math.PI / 2 - halfSpan;
    const a1 = Math.PI / 2 + halfSpan;
    const mid = (r0 + r1) / 2;
    const cap = (r1 - r0) / 2;
    const shape = new THREE.Shape();
    shape.moveTo(Math.cos(a0) * r1, Math.sin(a0) * r1);
    shape.absarc(0, 0, r1, a0, a1, false);
    // Rounded end: a half circle round the end of the band.
    shape.absarc(Math.cos(a1) * mid, Math.sin(a1) * mid, cap, a1, a1 + Math.PI, false);
    shape.absarc(0, 0, r0, a1, a0, true);
    shape.absarc(Math.cos(a0) * mid, Math.sin(a0) * mid, cap, a0 + Math.PI, a0 + Math.PI * 2, false);
    shape.closePath();
    const bevel = Math.min(0.03, height * 0.3);
    const g = new THREE.ExtrudeGeometry(shape, { depth: Math.max(0.001, height - bevel * 2), bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel, bevelSegments: 2, curveSegments: 48 });
    g.rotateX(-Math.PI / 2);
    g.translate(0, bevel, 0);
    return g;
  });
  return new THREE.Mesh(geo, mat);
}

/** Glass: see-through in the middle, bright toward the rim, with a highlight. */
function globeMaterial(hex) {
  const key = `globe|${hex}`;
  let mat = _materials.get(key);
  if (mat) return mat;
  const tint = new THREE.Color(hex);
  mat = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    uniforms: {
      body: { value: tint.clone().multiplyScalar(0.55) },
      rim: { value: new THREE.Color('#9fd2ff').multiplyScalar(1.25) },
    },
    vertexShader: `varying vec3 vN;
      void main() { vN = normalize(normalMatrix * normal); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform vec3 body; uniform vec3 rim; varying vec3 vN;
      void main() {
        vec3 n = normalize(vN);
        float f = pow(1.0 - clamp(n.z, 0.0, 1.0), 2.4);
        vec3 h = normalize(vec3(-0.35, 0.55, 1.0));
        float spec = pow(max(dot(n, h), 0.0), 90.0) * 0.9;
        float lift = 0.5 + 0.5 * n.y;
        vec3 c = body * (0.7 + 0.6 * lift) + rim * f + vec3(spec);
        gl_FragColor = vec4(c, clamp(0.32 + 0.65 * f + spec, 0.0, 1.0));
      }`,
  });
  _materials.set(key, mat);
  return mat;
}

/** A blue console screen: a header bar, a chart and rows of text. */
function hubScreenTexture(hex) {
  const key = `hub-ui|${hex}`;
  let tex = _iconTextures.get(key);
  if (tex) return tex;
  const canvas = document.createElement('canvas');
  canvas.width = 128;
  canvas.height = 80;
  const c = canvas.getContext('2d');
  const g = c.createLinearGradient(0, 0, 0, 80);
  g.addColorStop(0, '#1d4fa8');
  g.addColorStop(1, '#0f2f6e');
  c.fillStyle = g;
  c.fillRect(0, 0, 128, 80);
  c.fillStyle = '#5ea8ff';
  c.fillRect(6, 6, 116, 8);
  c.strokeStyle = '#9fd2ff';
  c.lineWidth = 2;
  c.beginPath();
  [[8, 58], [24, 46], [38, 52], [54, 32], [70, 40], [84, 26]].forEach(([x, y], i) => (i ? c.lineTo(x, y) : c.moveTo(x, y)));
  c.stroke();
  c.fillStyle = '#4b8ff0';
  for (let i = 0; i < 4; i += 1) c.fillRect(94, 22 + i * 12, 26 - (i % 2) * 8, 5);
  c.fillRect(8, 66, 70, 5);
  tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  _iconTextures.set(key, tex);
  return tex;
}

/**
 * A shooting star: a bright head and a tapering trail that fades toward
 * its tail, drawn additively. `userData.place(from, dir, head, trail, fade)`
 * puts the head `head` units from `from` along `dir` (flat, x/z), with a
 * trail `trail` long behind it, at `fade` (0-1) brightness.
 */
export function makeShootingStar() {
  const group = new THREE.Group();
  let trailMat = _materials.get('shooting-trail');
  if (!trailMat) {
    const canvas = document.createElement('canvas');
    canvas.width = 128;
    canvas.height = 16;
    const c = canvas.getContext('2d');
    for (let x = 0; x < 128; x += 1) {
      const along = x / 127;
      // Fainter and thinner toward the tail (x = 0).
      const a = Math.pow(along, 1.6);
      const half = 1 + along * 6;
      const g = c.createLinearGradient(0, 8 - half, 0, 8 + half);
      g.addColorStop(0, 'rgba(190,215,255,0)');
      g.addColorStop(0.5, `rgba(235,244,255,${a.toFixed(3)})`);
      g.addColorStop(1, 'rgba(190,215,255,0)');
      c.fillStyle = g;
      c.fillRect(x, 8 - half, 1, half * 2);
    }
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    trailMat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false, side: THREE.DoubleSide });
    _materials.set('shooting-trail', trailMat);
  }
  const trail = new THREE.Mesh(geometry('shooting-trail', () => new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2)), trailMat);
  group.add(trail);
  const headMat = glowMaterial('#eef5ff', 1.3, { opacity: 1, additive: true });
  const head = new THREE.Mesh(geometry('shooting-head', () => new THREE.SphereGeometry(0.16, 12, 8)), headMat);
  group.add(head);
  group.renderOrder = -1;
  group.userData.place = (from, dir, along, length, fade) => {
    const angle = Math.atan2(dir.z, dir.x);
    trail.rotation.y = -angle;
    trail.scale.set(Math.max(0.01, length), 1, 0.28);
    trail.position.set(from.x + dir.x * (along - length / 2), from.y, from.z + dir.z * (along - length / 2));
    head.position.set(from.x + dir.x * along, from.y, from.z + dir.z * along);
    trailMat.opacity = 0.75 * fade;
    head.scale.setScalar(0.4 + 0.6 * fade);
  };
  return group;
}

/**
 * A delegation packet: a glowing orb with two fading followers, moved by
 * scene.js along the route from the conductor's globe to a desk (or back).
 */
export function makePacket(color) {
  const group = new THREE.Group();
  const head = new THREE.Mesh(geometry('packet-head', () => new THREE.SphereGeometry(0.3, 16, 12)), glowMaterial(color, 1.5));
  group.add(head);
  [0.7, 0.45].forEach((k, i) => {
    const tail = new THREE.Mesh(geometry('packet-head', () => new THREE.SphereGeometry(0.3, 16, 12)), glowMaterial(color, 1.2, { opacity: 0.55 - i * 0.2, additive: true }));
    tail.scale.setScalar(k);
    group.add(tail);
  });
  group.userData.trail = group.children.slice(1);
  return group;
}

/** A status beacon over a figure's head: a small glowing gem. */
export function makeBeacon() {
  const mesh = new THREE.Mesh(geometry('beacon', () => new THREE.OctahedronGeometry(0.2, 0)), glowMaterial('#22c55e', 1.3));
  mesh.visible = false;
  return mesh;
}

/** The beacon's colour for a worker status (null hides it). */
export function beaconColor(status) {
  switch (status) {
    case 'running': return '#22c55e';
    case 'completed': return '#60a5fa';
    case 'failed': case 'error': case 'timeout': return '#ef4444';
    default: return null;
  }
}

export function beaconMaterial(color) {
  return glowMaterial(color, 1.3);
}

/**
 * A field of faint stars scattered over the floor around the office. Each
 * twinkles on its own slow cycle (a phase and speed per star, animated in
 * the shader from one `time` uniform), dimming to about half and back; one
 * in ten is a larger, brighter star.
 */
export function makeStarfield(halfSize, count, opts) {
  const options = opts || {};
  const n = count || 900;
  const positions = new Float32Array(n * 3);
  const colors = new Float32Array(n * 3);
  const twinkle = new Float32Array(n * 3);
  let seed = options.seed || 7;
  const rand = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  const blue = new THREE.Color('#7aa2ff');
  const white = new THREE.Color('#dbe6ff');
  for (let i = 0; i < n; i += 1) {
    positions[i * 3] = (rand() * 2 - 1) * halfSize;
    positions[i * 3 + 1] = 0.05;
    positions[i * 3 + 2] = (rand() * 2 - 1) * halfSize;
    const c = rand() < 0.6 ? blue : white;
    // Brighter than they were (they were lost on the dark backdrop), and one
    // in ten a larger, brighter star so the field has some that catch the eye.
    const bright = rand() < 0.1;
    const k = bright ? 1 : 0.55 + rand() * 0.4;
    colors[i * 3] = c.r * k; colors[i * 3 + 1] = c.g * k; colors[i * 3 + 2] = c.b * k;
    twinkle[i * 3] = rand() * Math.PI * 2;
    twinkle[i * 3 + 1] = 0.6 + rand() * 1.6;
    twinkle[i * 3 + 2] = bright ? 1.9 : 1;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.setAttribute('twinkle', new THREE.BufferAttribute(twinkle, 3));
  const mat = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    uniforms: { time: { value: 0 }, size: { value: options.size || 2.6 } },
    vertexShader: `attribute vec3 color; attribute vec3 twinkle; uniform float time; uniform float size;
      varying vec3 vColor; varying float vLight;
      void main() {
        vColor = color;
        float s = 0.5 + 0.5 * sin(time * twinkle.y + twinkle.x);
        vLight = 0.55 + 0.45 * s * s;
        gl_PointSize = size * twinkle.z * (0.85 + 0.35 * s);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `varying vec3 vColor; varying float vLight;
      void main() {
        float d = length(gl_PointCoord - 0.5);
        // A bright centre with a soft edge, so a star reads as a point of light.
        float a = smoothstep(0.5, 0.1, d);
        if (a <= 0.0) discard;
        float core = smoothstep(0.25, 0.0, d);
        gl_FragColor = vec4(vColor * vLight * (1.7 + core * 0.8), a);
      }`,
  });
  const points = new THREE.Points(geo, mat);
  points.userData.owned = { geometry: geo, material: mat };
  return points;
}
