// Job Logistics Centre — the Job OS pipeline as a small 3D warehouse.
//
// Every job is a parcel. Parcels sit in the zone that matches their lifecycle
// status and ride the conveyor when that status changes between refreshes:
// Receiving dock (found) → Sorting floor (Luna scanned) → Tailoring workshop
// → Approval gate → Shipping bay (applied and beyond). Colour is the fit
// score's verdict.
//
// The scene draws; it never fetches. index.js hands it the job list on each
// refresh. mountLogistics() returns the owner of every GPU resource: dispose()
// stops the loop and releases geometries, materials, textures and the WebGL
// context, so leaving the view frees the GPU (same contract as the Office).
import * as THREE from 'three';

const ZONES = [
  {key: 'receiving', label: 'Receiving dock', hint: 'Found by Scout', x: -52, statuses: ['discovered', 'scraped'], tint: 0x5b6b8c},
  {key: 'sorting', label: 'Sorting floor', hint: 'Scored by Luna', x: -26, statuses: ['analyzed'], tint: 0x6b5bd6},
  {key: 'tailoring', label: 'Tailoring workshop', hint: 'Resume being fitted', x: 0, statuses: ['shortlisted', 'tailoring', 'resume_ready'], tint: 0xd69a2d},
  {key: 'approval', label: 'Approval gate', hint: 'Waiting to send', x: 26, statuses: ['application_ready', 'awaiting_approval', 'applying'], tint: 0xe0663a},
  {key: 'shipping', label: 'Shipping bay', hint: 'Applied and beyond', x: 52, statuses: ['submitted', 'screening', 'interviewing', 'offer', 'offer_accepted'], tint: 0x3aa76d},
];
const ZONE_OF = Object.fromEntries(ZONES.flatMap((z) => z.statuses.map((s) => [s, z])));
const VERDICT_COLORS = {strong: 0x4ade80, good: 0xffd21f, stretch: 0xf5a524, poor: 0xf07878};
const NO_SCORE = 0x9aa3b2;
const PARCEL = 2.7;
const BELT_Y = 2.2;
const PER_ZONE = 32; // parcels drawn per zone; the rest are counted on the label
const FRUSTUM = 47;
const ISO = new THREE.Vector3(1, 0.95, 1.15).normalize();

export function mountLogistics(host, {onOpenJob} = {}) {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({antialias: true, alpha: false, powerPreference: 'low-power'});
  } catch (error) {
    host.innerHTML = '<p class="logistics-fallback">3D view needs WebGL, which this browser has turned off.</p>';
    return {update() {}, dispose() { host.innerHTML = ''; }};
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const canvas = renderer.domElement;
  canvas.className = 'logistics-canvas';
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', 'Job Logistics Centre: each parcel is a job, placed in the zone for its current stage');
  host.appendChild(canvas);
  const overlay = document.createElement('div');
  overlay.className = 'logistics-overlay';
  host.appendChild(overlay);
  const tip = document.createElement('div');
  tip.className = 'logistics-tip';
  tip.hidden = true;
  host.appendChild(tip);

  const scene = new THREE.Scene();
  const css = getComputedStyle(document.documentElement);
  const bg = new THREE.Color(css.getPropertyValue('--bg').trim() || '#0f1018');
  scene.background = bg;
  scene.fog = new THREE.Fog(bg, 260, 420);
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 1, 1000);
  // Aim a little behind the floor's centre so the back-wall towers stay in frame.
  const target = new THREE.Vector3(4, 6, -6);
  camera.position.copy(ISO).multiplyScalar(240).add(target);
  camera.lookAt(target);

  // ---- lights ----
  scene.add(new THREE.HemisphereLight(0xdfe7ff, 0x2a2430, 1.15));
  const sun = new THREE.DirectionalLight(0xffffff, 2.1);
  sun.position.set(60, 110, 70);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  Object.assign(sun.shadow.camera, {left: -90, right: 90, top: 70, bottom: -70, near: 10, far: 300});
  scene.add(sun);

  // ---- shared materials ----
  const mat = (color, extra) => new THREE.MeshStandardMaterial({color, roughness: 0.8, metalness: 0.08, ...extra});
  const M = {
    floor: mat(0x262833, {roughness: 0.95}), pad: null, steel: mat(0x6f7787, {metalness: 0.5, roughness: 0.45}),
    dark: mat(0x30343f), wall: mat(0x3a3e4b), yellow: mat(0xffd21f), white: mat(0xe9edf5),
    glass: mat(0x8fd3ff, {emissive: 0x3aa0ff, emissiveIntensity: 0.6, transparent: true, opacity: 0.75}),
    red: mat(0xe0453a, {emissive: 0xe0453a, emissiveIntensity: 0.5}), green: mat(0x3fcf73, {emissive: 0x3fcf73, emissiveIntensity: 0.5}),
  };
  const box = (w, h, d, material, x = 0, y = 0, z = 0, parent = scene) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
    mesh.position.set(x, y, z);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    parent.add(mesh);
    return mesh;
  };
  const cyl = (rt, rb, h, material, x, y, z, parent = scene, seg = 16) => {
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, seg), material);
    mesh.position.set(x, y, z);
    mesh.castShadow = true;
    parent.add(mesh);
    return mesh;
  };

  // ---- floor, walls, zone pads ----
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(220, 150), M.floor);
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);
  const grid = new THREE.GridHelper(220, 44, 0x3b3f4d, 0x30333e);
  grid.position.y = 0.02;
  scene.add(grid);
  box(150, 14, 1.2, M.wall, 0, 7, -40);
  box(1.2, 14, 80, M.wall, -75, 7, 0);
  for (const zone of ZONES) {
    const pad = new THREE.Mesh(new THREE.PlaneGeometry(22, 30),
      new THREE.MeshStandardMaterial({color: zone.tint, transparent: true, opacity: 0.22, roughness: 1}));
    pad.rotation.x = -Math.PI / 2;
    pad.position.set(zone.x, 0.05, 12);
    pad.receiveShadow = true;
    scene.add(pad);
    const stripe = new THREE.Mesh(new THREE.PlaneGeometry(22, 0.6), new THREE.MeshBasicMaterial({color: zone.tint}));
    stripe.rotation.x = -Math.PI / 2;
    stripe.position.set(zone.x, 0.06, 27);
    scene.add(stripe);
  }

  // ---- conveyor (belt texture scrolls) ----
  const beltCanvas = document.createElement('canvas');
  beltCanvas.width = 128; beltCanvas.height = 32;
  const bctx = beltCanvas.getContext('2d');
  bctx.fillStyle = '#1d1f26'; bctx.fillRect(0, 0, 128, 32);
  bctx.fillStyle = '#2c2f39';
  for (let i = 0; i < 128; i += 16) bctx.fillRect(i, 0, 6, 32);
  const beltTexture = new THREE.CanvasTexture(beltCanvas);
  beltTexture.wrapS = beltTexture.wrapT = THREE.RepeatWrapping;
  beltTexture.repeat.set(30, 1);
  const belt = box(130, 0.5, 4, new THREE.MeshStandardMaterial({map: beltTexture, roughness: 0.9}), 0, BELT_Y - 0.25, -6);
  for (let x = -64; x <= 64; x += 8) { box(0.6, BELT_Y - 0.5, 0.6, M.steel, x, (BELT_Y - 0.5) / 2, -8); box(0.6, BELT_Y - 0.5, 0.6, M.steel, x, (BELT_Y - 0.5) / 2, -4); }
  box(130, 0.4, 0.3, M.yellow, 0, BELT_Y + 0.1, -8.2);
  box(130, 0.4, 0.3, M.yellow, 0, BELT_Y + 0.1, -3.8);

  // ---- props ----
  const truck = (x, z, color, facing) => {
    const g = new THREE.Group();
    box(14, 7, 6, mat(color), 0, 4.2, 0, g);
    box(4.5, 5, 5.6, M.white, facing * 9.5, 3.2, 0, g);
    box(0.2, 2, 4.4, M.glass, facing * 11.8, 4.2, 0, g);
    for (const wx of [-4.5, 4.5, facing * 9.5]) for (const wz of [-3, 3]) {
      const wheel = cyl(1.1, 1.1, 0.8, M.dark, wx, 1.1, wz, g);
      wheel.rotation.x = Math.PI / 2;
    }
    g.position.set(x, 0, z);
    scene.add(g);
    return g;
  };
  // Receiving: dock door and an inbound truck.
  box(14, 11, 1, M.dark, -52, 5.5, -39);
  box(12, 9, 0.4, mat(0x4a5163), -52, 4.5, -38.4);
  truck(-66, -22, 0x5b6b8c, 1).rotation.y = Math.PI / 2;
  // Sorting: Luna's scanner arch with a sweeping light.
  box(1.2, 9, 1.2, M.steel, -26, 4.5, -9.5); box(1.2, 9, 1.2, M.steel, -26, 4.5, -2.5); box(1.6, 1.2, 8.4, M.steel, -26, 9, -6);
  const scanBar = box(0.5, 0.4, 6.6, new THREE.MeshBasicMaterial({color: 0x9f8cff}), -26, 7.6, -6);
  const scanLight = new THREE.PointLight(0x8c7bff, 30, 18, 2);
  scanLight.position.set(-26, 6, -6);
  scene.add(scanLight);
  // Tailoring: a bench with a robot arm that works while résumés are being fitted.
  box(10, 3, 5, M.steel, 0, 1.5, -16);
  const armBase = cyl(1.2, 1.6, 1.5, M.yellow, 2, 3.75, -16);
  const arm = new THREE.Group();
  arm.position.set(2, 4.5, -16);
  scene.add(arm);
  const upper = box(0.9, 6, 0.9, M.yellow, 0, 3, 0, arm);
  const forearm = new THREE.Group();
  forearm.position.set(0, 6, 0);
  arm.add(forearm);
  box(4.5, 0.8, 0.8, M.yellow, -2.25, 0, 0, forearm);
  box(0.6, 1.4, 1.4, M.dark, -4.6, -0.6, 0, forearm);
  void armBase; void upper;
  // Approval gate: two posts, a barrier arm and a signal light.
  box(1.2, 6, 1.2, M.dark, 26, 3, -9.8); box(1.2, 6, 1.2, M.dark, 26, 3, -2.2);
  const barrierPivot = new THREE.Group();
  barrierPivot.position.set(26, 5.2, -9.8);
  scene.add(barrierPivot);
  const barrier = box(0.4, 0.5, 8.4, mat(0xe9edf5), 0, 0, 4.2, barrierPivot);
  for (let i = 0; i < 4; i += 1) box(0.45, 0.55, 1, M.red, 0, 0, 1 + i * 2, barrierPivot);
  void barrier;
  const signal = new THREE.Mesh(new THREE.SphereGeometry(0.8, 16, 12), M.red);
  signal.position.set(26, 6.8, -9.8);
  scene.add(signal);
  // Shipping: outbound truck.
  const outTruck = truck(66, -22, 0x3aa76d, -1);
  outTruck.rotation.y = -Math.PI / 2;
  box(14, 11, 1, M.dark, 52, 5.5, -39);
  // Mail tower with a beacon: pulses while something waits for you.
  cyl(1.2, 1.8, 26, M.steel, 40, 13, -32);
  box(5, 3.5, 5, M.wall, 40, 27, -32);
  const beacon = new THREE.Mesh(new THREE.SphereGeometry(1.1, 16, 12), new THREE.MeshStandardMaterial({color: 0xffd21f, emissive: 0xffd21f, emissiveIntensity: 0.3}));
  beacon.position.set(40, 30, -32);
  scene.add(beacon);
  // Clock tower showing the real time.
  box(5, 26, 5, M.wall, -40, 13, -32);
  const clockCanvas = document.createElement('canvas');
  clockCanvas.width = clockCanvas.height = 128;
  const clockTexture = new THREE.CanvasTexture(clockCanvas);
  const face = new THREE.Mesh(new THREE.PlaneGeometry(4.4, 4.4), new THREE.MeshBasicMaterial({map: clockTexture}));
  face.position.set(-40, 22, -29.4);
  scene.add(face);
  const faceSide = face.clone();
  faceSide.position.set(-37.4, 22, -32);
  faceSide.rotation.y = Math.PI / 2;
  scene.add(faceSide);
  let lastMinute = -1;
  function drawClock() {
    const now = new Date();
    if (now.getMinutes() === lastMinute) return;
    lastMinute = now.getMinutes();
    const c = clockCanvas.getContext('2d');
    c.fillStyle = '#f4f1e6'; c.beginPath(); c.arc(64, 64, 62, 0, Math.PI * 2); c.fill();
    c.strokeStyle = '#1d1f26'; c.lineWidth = 4; c.stroke();
    for (let i = 0; i < 12; i += 1) { const a = (i / 12) * Math.PI * 2; c.fillStyle = '#1d1f26'; c.fillRect(64 + Math.sin(a) * 50 - 2, 64 - Math.cos(a) * 50 - 2, 4, 4); }
    const hand = (angle, length, width) => { c.lineWidth = width; c.lineCap = 'round'; c.beginPath(); c.moveTo(64, 64); c.lineTo(64 + Math.sin(angle) * length, 64 - Math.cos(angle) * length); c.stroke(); };
    hand(((now.getHours() % 12) + now.getMinutes() / 60) / 12 * Math.PI * 2, 30, 6);
    hand(now.getMinutes() / 60 * Math.PI * 2, 44, 4);
    clockTexture.needsUpdate = true;
  }
  drawClock();
  // Control desk with a status screen.
  box(12, 3, 5, M.dark, 0, 1.5, 34);
  const screenCanvas = document.createElement('canvas');
  screenCanvas.width = 256; screenCanvas.height = 128;
  const screenTexture = new THREE.CanvasTexture(screenCanvas);
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(9, 4.5), new THREE.MeshBasicMaterial({map: screenTexture}));
  screen.position.set(0, 5.6, 33);
  screen.rotation.x = -0.25;
  scene.add(screen);
  box(9.6, 5, 0.4, M.dark, 0, 5.6, 32.7).rotation.x = -0.25;
  function drawScreen(counts, total) {
    const c = screenCanvas.getContext('2d');
    c.fillStyle = '#0b1220'; c.fillRect(0, 0, 256, 128);
    c.fillStyle = '#7dd3fc'; c.font = 'bold 18px system-ui, sans-serif'; c.fillText(`${total} parcels on the floor`, 12, 26);
    c.font = '14px system-ui, sans-serif';
    ZONES.forEach((z, i) => { c.fillStyle = '#' + z.tint.toString(16).padStart(6, '0'); c.fillRect(12, 40 + i * 17, 10, 10); c.fillStyle = '#e2e8f0'; c.fillText(`${z.label}: ${counts[z.key] || 0}`, 28, 50 + i * 17); });
    screenTexture.needsUpdate = true;
  }

  // ---- zone labels (HTML, projected) ----
  const labels = ZONES.map((zone) => {
    const el = document.createElement('div');
    el.className = 'logistics-label';
    el.innerHTML = `<strong></strong><small></small>`;
    el.querySelector('strong').textContent = zone.label;
    overlay.appendChild(el);
    return {zone, el, count: 0};
  });
  function placeLabels() {
    const rect = canvas.getBoundingClientRect();
    const hostRect = host.getBoundingClientRect();
    const offset = rect.left - hostRect.left; // the canvas can be wider than the stage mid-slide
    const v = new THREE.Vector3();
    for (const label of labels) {
      v.set(label.zone.x, 0, 30).project(camera);
      const half = label.el.offsetWidth / 2 + 6; // keep labels inside the stage on narrow screens
      const x = Math.min(hostRect.width - half, Math.max(half, offset + (v.x + 1) / 2 * rect.width));
      label.el.style.transform = `translate(-50%, 0) translate(${x}px, ${(1 - v.y) / 2 * rect.height}px)`;
    }
  }

  // ---- parcels ----
  const parcelGeometry = new THREE.BoxGeometry(PARCEL, PARCEL * 0.8, PARCEL);
  const tapeGeometry = new THREE.BoxGeometry(PARCEL * 1.01, PARCEL * 0.82, 0.35);
  const tapeMaterial = mat(0xc9a66b);
  const parcelMaterials = new Map();
  const materialFor = (color) => {
    if (!parcelMaterials.has(color)) parcelMaterials.set(color, mat(color, {roughness: 0.7}));
    return parcelMaterials.get(color);
  };
  const parcels = new Map(); // job id -> {mesh, job, zoneKey, anim}
  const slotPosition = (zone, index) => {
    const col = index % 4, row = Math.floor(index / 4) % 4, layer = Math.floor(index / 16);
    return new THREE.Vector3(zone.x - 5.25 + col * 3.5, PARCEL * 0.4 + layer * PARCEL * 0.82, 4 + row * 3.4);
  };
  function makeParcel(job) {
    const mesh = new THREE.Mesh(parcelGeometry, materialFor(colorOf(job)));
    mesh.castShadow = true; mesh.receiveShadow = true;
    const tape = new THREE.Mesh(tapeGeometry, tapeMaterial);
    mesh.add(tape);
    mesh.userData.jobId = job.id;
    scene.add(mesh);
    return mesh;
  }
  const colorOf = (job) => (job.analysis && job.analysis.fit_score != null ? (VERDICT_COLORS[job.analysis.verdict] || NO_SCORE) : NO_SCORE);

  let firstUpdate = true;
  let gateOpenUntil = 0;
  let truckLeaveAt = 0;
  function update(jobs) {
    const byZone = Object.fromEntries(ZONES.map((z) => [z.key, []]));
    for (const job of jobs || []) { const zone = ZONE_OF[job.status]; if (zone) byZone[zone.key].push(job); }
    const counts = {};
    const seen = new Set();
    const now = performance.now();
    let total = 0;
    for (const zone of ZONES) {
      const list = byZone[zone.key].sort((a, b) => String(a.created_at || a.id).localeCompare(String(b.created_at || b.id)));
      counts[zone.key] = list.length;
      total += list.length;
      list.slice(-PER_ZONE).forEach((job, index) => {
        seen.add(job.id);
        const target = slotPosition(zone, index);
        let parcel = parcels.get(job.id);
        if (!parcel) {
          parcel = {mesh: makeParcel(job), job, zoneKey: zone.key, anim: null};
          parcels.set(job.id, parcel);
          if (firstUpdate || reduced) parcel.mesh.position.copy(target);
          else parcel.anim = {kind: 'drop', from: target.clone().setY(target.y + 30), to: target, start: now, duration: 900};
          if (!firstUpdate && !reduced) parcel.mesh.position.copy(parcel.anim.from);
          if (firstUpdate && !reduced) { parcel.anim = {kind: 'drop', from: target.clone().setY(target.y + 18), to: target, start: now + index * 35 + ZONES.indexOf(zone) * 120, duration: 650}; parcel.mesh.position.copy(parcel.anim.from); }
        } else {
          parcel.mesh.material = materialFor(colorOf(job));
          const moved = parcel.zoneKey !== zone.key;
          const settled = parcel.anim ? parcel.anim.to : parcel.mesh.position;
          if (moved && !reduced) {
            parcel.anim = {kind: 'ride', from: parcel.mesh.position.clone(), to: target, start: now, duration: 1400 + Math.abs(zone.x - ZONE_BY_KEY[parcel.zoneKey].x) * 22};
            if (zone.key === 'shipping') truckLeaveAt = now + parcel.anim.duration;
            if (ZONES.indexOf(zone) > ZONES.indexOf(ZONE_BY_KEY.approval) && ZONES.indexOf(ZONE_BY_KEY[parcel.zoneKey]) <= ZONES.indexOf(ZONE_BY_KEY.approval)) gateOpenUntil = now + parcel.anim.duration + 600;
          } else if (!settled.equals(target)) {
            if (reduced) parcel.mesh.position.copy(target);
            else parcel.anim = {kind: 'slide', from: parcel.mesh.position.clone(), to: target, start: now, duration: 500};
          }
          parcel.zoneKey = zone.key;
        }
        parcel.job = job;
      });
    }
    for (const [id, parcel] of parcels) {
      if (seen.has(id)) continue;
      scene.remove(parcel.mesh);
      parcels.delete(id);
    }
    for (const label of labels) {
      const n = counts[label.zone.key] || 0;
      label.el.querySelector('small').textContent = `${n} · ${label.zone.hint}${n > PER_ZONE ? ` (showing ${PER_ZONE})` : ''}`;
    }
    working.tailoring = (byZone.tailoring || []).some((j) => j.status === 'tailoring');
    working.waiting = (byZone.approval || []).some((j) => j.status === 'awaiting_approval');
    working.applying = (byZone.approval || []).some((j) => j.status === 'applying');
    drawScreen(counts, total);
    firstUpdate = false;
    wake();
  }
  const ZONE_BY_KEY = Object.fromEntries(ZONES.map((z) => [z.key, z]));
  const working = {tailoring: false, waiting: false, applying: false};

  // ---- camera framing, resize, zoom ----
  let zoom = 1;
  // While the sidebar slides, the stage changes width every frame. Reallocating
  // the WebGL drawing buffer each time would stutter (and blank), so the canvas
  // keeps the widest width the stage reaches during the slide, centred in the
  // clipping stage; only the visible window changes. The camera's vertical
  // extent is fixed, so the centred part is exactly what the final, narrower
  // canvas shows and the single resize after the slide is seamless.
  function slideSpan() {
    const layout = document.querySelector('.layout');
    const main = document.querySelector('.main');
    const max = layout && layout.classList.contains('panel-sliding') ? Number(layout.dataset.slideMainMax) : 0;
    if (!max || !main) return 0;
    return Math.max(host.clientWidth, Math.round(host.clientWidth + max - main.clientWidth));
  }
  let bufferW = 0, bufferH = 0;
  function resize() {
    const span = slideSpan();
    const w = span || host.clientWidth || 1, h = host.clientHeight || 1;
    if (span) {
      canvas.style.cssText = `width:${span}px;max-width:none;position:absolute;left:50%;transform:translateX(-50%);`;
    } else if (canvas.style.cssText) {
      canvas.style.cssText = '';
    }
    const resized = w !== bufferW || h !== bufferH;
    if (resized) { renderer.setSize(w, h, false); bufferW = w; bufferH = h; }
    const aspect = w / h;
    // Fit the 150-unit-wide floor on narrow screens; keep a constant scale on wide ones.
    const half = Math.max(FRUSTUM, 60 / aspect);
    camera.left = -half * aspect; camera.right = half * aspect; camera.top = half; camera.bottom = -half;
    camera.zoom = zoom;
    camera.updateProjectionMatrix();
    placeLabels();
    // Resizing clears the drawing buffer; paint now so no blank frame shows.
    if (resized) renderer.render(scene, camera);
    wake();
  }
  const observer = new ResizeObserver(resize);
  observer.observe(host);
  // The host's size may not change when a slide ends, but the canvas leaves
  // its slide-time span then: settle it.
  const layoutEl = document.querySelector('.layout');
  let wasSliding = false;
  const slideObserver = layoutEl ? new MutationObserver(() => {
    const sliding = layoutEl.classList.contains('panel-sliding');
    if (sliding !== wasSliding) { wasSliding = sliding; resize(); }
  }) : null;
  if (slideObserver) slideObserver.observe(layoutEl, {attributes: true, attributeFilter: ['class']});
  function onWheel(event) {
    event.preventDefault();
    zoom = Math.min(2.6, Math.max(0.7, zoom * (event.deltaY > 0 ? 0.9 : 1.1)));
    camera.zoom = zoom;
    camera.updateProjectionMatrix();
    placeLabels();
    wake();
  }
  canvas.addEventListener('wheel', onWheel, {passive: false});

  // ---- picking ----
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let hovered = null;
  function pick(event) {
    const rect = canvas.getBoundingClientRect();
    pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects([...parcels.values()].map((p) => p.mesh), false)[0];
    return hit ? parcels.get(hit.object.userData.jobId) : null;
  }
  function onMove(event) {
    const parcel = pick(event);
    if (hovered && hovered !== parcel) hovered.mesh.scale.setScalar(1);
    hovered = parcel;
    canvas.style.cursor = parcel ? 'pointer' : '';
    if (!parcel) { tip.hidden = true; wake(); return; }
    parcel.mesh.scale.setScalar(1.18);
    const job = parcel.job;
    const fit = job.analysis && job.analysis.fit_score != null ? ` · fit ${job.analysis.fit_score}` : '';
    tip.textContent = '';
    const strong = document.createElement('strong');
    strong.textContent = job.title || 'Untitled job';
    const small = document.createElement('small');
    small.textContent = `${[job.company, String(job.status || '').replace(/_/g, ' ')].filter(Boolean).join(' · ')}${fit}`;
    tip.append(strong, small);
    const rect = host.getBoundingClientRect();
    tip.style.left = `${event.clientX - rect.left + 14}px`;
    tip.style.top = `${event.clientY - rect.top + 14}px`;
    tip.hidden = false;
    wake();
  }
  function onLeave() { if (hovered) hovered.mesh.scale.setScalar(1); hovered = null; tip.hidden = true; wake(); }
  function onClick(event) { const parcel = pick(event); if (parcel && onOpenJob) onOpenJob(parcel.job.id); }
  canvas.addEventListener('pointermove', onMove);
  canvas.addEventListener('pointerleave', onLeave);
  canvas.addEventListener('click', onClick);

  // ---- loop ----
  const ease = (t) => 1 - Math.pow(1 - t, 3);
  const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  let raf = 0;
  let disposed = false;
  let gateAngle = 0;
  let truckOffset = 0;
  function step(now) {
    raf = 0;
    if (disposed) return;
    // Hidden panel or tab: stop drawing until something wakes the loop again.
    if (document.hidden || !host.isConnected || host.offsetParent === null) return;
    let animating = false;
    for (const parcel of parcels.values()) {
      const a = parcel.anim;
      if (!a) continue;
      if (now < a.start) { animating = true; continue; }
      const t = Math.min(1, (now - a.start) / a.duration);
      const p = parcel.mesh.position;
      if (a.kind === 'ride') {
        // Up onto the belt, along it, then down into the new slot.
        const lift = 0.18, land = 0.82;
        if (t < lift) { const k = ease(t / lift); p.set(a.from.x, a.from.y + (BELT_Y + PARCEL * 0.4 - a.from.y) * k, a.from.z + (-6 - a.from.z) * k); }
        else if (t < land) { const k = easeInOut((t - lift) / (land - lift)); p.set(a.from.x + (a.to.x - a.from.x) * k, BELT_Y + PARCEL * 0.4, -6); }
        else { const k = ease((t - land) / (1 - land)); p.set(a.to.x, BELT_Y + PARCEL * 0.4 + (a.to.y - BELT_Y - PARCEL * 0.4) * k, -6 + (a.to.z + 6) * k); }
        parcel.mesh.rotation.y = t < 1 ? Math.sin(t * Math.PI) * 0.3 : 0;
      } else {
        p.lerpVectors(a.from, a.to, a.kind === 'drop' ? ease(t) : easeInOut(t));
      }
      if (t >= 1) { p.copy(a.to); parcel.anim = null; } else animating = true;
    }
    const ambient = !reduced;
    if (ambient) {
      beltTexture.offset.x -= 0.004;
      scanBar.position.x = -26 + Math.sin(now / 700) * 0.6;
      scanLight.intensity = 22 + Math.sin(now / 300) * 8;
      const work = working.tailoring ? 1 : 0.15;
      arm.rotation.y = Math.sin(now / 900) * 0.9 * work;
      forearm.rotation.z = -0.4 + Math.sin(now / 450) * 0.35 * work;
      beacon.material.emissiveIntensity = working.waiting ? 0.6 + Math.sin(now / 250) * 0.6 : 0.25;
    }
    const gateTarget = working.applying || now < gateOpenUntil ? -Math.PI / 2.2 : 0;
    gateAngle += (gateTarget - gateAngle) * (reduced ? 1 : 0.08);
    barrierPivot.rotation.x = gateAngle;
    signal.material = gateTarget ? M.green : M.red;
    if (!reduced && now > truckLeaveAt && truckLeaveAt) {
      const k = Math.min(1, (now - truckLeaveAt) / 2600);
      truckOffset = Math.sin(k * Math.PI) * 26;
      if (k >= 1) truckLeaveAt = 0; else animating = true;
    }
    outTruck.position.z = -22 - truckOffset * 0.4;
    outTruck.position.x = 66 + truckOffset;
    drawClock();
    renderer.render(scene, camera);
    if (ambient || animating || Math.abs(gateTarget - gateAngle) > 0.001) raf = requestAnimationFrame(step);
  }
  function wake() { if (!raf && !disposed) raf = requestAnimationFrame(step); }
  const onVisibility = () => { if (!document.hidden) wake(); };
  document.addEventListener('visibilitychange', onVisibility);
  // The Jobs panel can be hidden without the view changing; check back cheaply.
  const heartbeat = setInterval(wake, 1500);
  resize();

  function dispose() {
    disposed = true;
    if (raf) cancelAnimationFrame(raf);
    clearInterval(heartbeat);
    observer.disconnect();
    if (slideObserver) slideObserver.disconnect();
    document.removeEventListener('visibilitychange', onVisibility);
    canvas.removeEventListener('wheel', onWheel);
    canvas.removeEventListener('pointermove', onMove);
    canvas.removeEventListener('pointerleave', onLeave);
    canvas.removeEventListener('click', onClick);
    const textures = new Set();
    scene.traverse((object) => {
      if (object.geometry) object.geometry.dispose();
      const materials = Array.isArray(object.material) ? object.material : object.material ? [object.material] : [];
      for (const m of materials) { if (m.map) textures.add(m.map); m.dispose(); }
    });
    for (const m of Object.values(M)) if (m) m.dispose();
    for (const m of parcelMaterials.values()) m.dispose();
    parcelGeometry.dispose(); tapeGeometry.dispose(); tapeMaterial.dispose();
    for (const t of textures) t.dispose();
    renderer.dispose();
    renderer.forceContextLoss();
    host.innerHTML = '';
  }
  return {update, dispose, get parcelCount() { return parcels.size; }, renderer};
}
