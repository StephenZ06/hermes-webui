// Office floor plan — where desks go (phase 3).
//
// Pure geometry: takes the adapter's desk list and returns world positions.
// No three.js, no DOM, so tests/test_office_layout.py can run the real thing
// under node the same way the adapter tests do.
//
// The Projects outlet has no fixed departments — the floor plan is a function
// of the live delegation tree, not a constant. Desks are grouped into pods by
// cluster (a subagent's parent), and pods are laid out on concentric rings
// around the conductor at the origin. This is the part the upstream reference
// gets wrong for our purposes: its LAYOUT and AGENTS are static module
// exports and the scene is built once from them, so it can only ever draw the
// office it was written with.
//
// Stability matters as much as packing: a new subagent must not make the
// existing office jump around, so pods keep their ring slot for as long as
// their cluster exists, in first-seen order.

/** World units between adjacent desks inside a pod. */
export const SEAT_SPACING_X = 9;
export const SEAT_SPACING_Z = 8;
/** Gap between a pod's edge and its ring neighbours. */
export const POD_GAP = 10;
/** Radius of the conductor's own pod at the centre. */
export const CONDUCTOR_RADIUS = 11;
/** Pods per ring. Ring 1 takes 6, ring 2 takes 12, and so on. */
const RING_BASE_CAPACITY = 6;
/**
 * Seats across a pod. Small pods stay narrow so a two-subagent branch reads
 * as a pair rather than a row; large ones widen toward square, because a
 * department with fifteen desks laid out three wide becomes a corridor five
 * rows deep that shoves every other pod off the floor.
 */
const MIN_POD_COLUMNS = 3;
const MAX_POD_COLUMNS = 6;

function podGrid(seatCount) {
  const square = Math.ceil(Math.sqrt(Math.max(1, seatCount)));
  const cols = Math.max(1, Math.min(
    seatCount, MAX_POD_COLUMNS, Math.max(MIN_POD_COLUMNS, square),
  ));
  const rows = Math.max(1, Math.ceil(seatCount / cols));
  return { cols, rows };
}

function podSize(seatCount) {
  const { cols, rows } = podGrid(seatCount);
  return {
    width: cols * SEAT_SPACING_X,
    depth: rows * SEAT_SPACING_Z,
  };
}

/**
 * Which ring a pod sits on, and its index within that ring.
 * Ring 1 holds 6 pods, ring 2 holds 12, ring r holds 6r.
 */
export function ringSlot(podIndex) {
  let ring = 1;
  let consumed = 0;
  for (;;) {
    const capacity = RING_BASE_CAPACITY * ring;
    if (podIndex < consumed + capacity) {
      return { ring, indexInRing: podIndex - consumed, capacity };
    }
    consumed += capacity;
    ring += 1;
  }
}

/**
 * Distance from the centre of an axis-aligned rectangular slab to its edge,
 * along a unit direction.
 *
 * Pods and the conductor's plinth are squares, not discs, so their edge is
 * further away on the diagonal than on the axis — using a single radius
 * leaves a walkway hanging short of some pods and overlapping others.
 *
 * @param {number} halfWidth half-extent along x
 * @param {number} halfDepth half-extent along z
 * @param {number} dirX unit direction x
 * @param {number} dirZ unit direction z
 */
export function slabEdgeDistance(halfWidth, halfDepth, dirX, dirZ) {
  const byX = Math.abs(dirX) > 1e-9 ? halfWidth / Math.abs(dirX) : Infinity;
  const byZ = Math.abs(dirZ) > 1e-9 ? halfDepth / Math.abs(dirZ) : Infinity;
  const edge = Math.min(byX, byZ);
  return isFinite(edge) ? edge : Math.max(halfWidth, halfDepth);
}

/**
 * The walkway joining a pod to the hub in the middle of the office.
 *
 * Returns where the slab starts and ends measured from the origin, so it can
 * be tucked slightly *under* both platforms rather than stopping at their
 * edges — a walkway that stops exactly on an edge still shows a hairline seam
 * where the two meet, and one that stops short of it reads as a broken bridge.
 *
 * @returns {{start:number, end:number, length:number, angle:number}|null}
 *   null when the pod is so close that no walkway would be visible.
 */
export function walkwaySpan(pod, hubHalfExtent, options) {
  const config = Object.assign({ overlap: 0.6, minLength: 1 }, options || {});
  const distance = Math.hypot(pod.x, pod.z);
  if (!(distance > 0)) return null;
  const dirX = pod.x / distance;
  const dirZ = pod.z / distance;

  const hubEdge = slabEdgeDistance(hubHalfExtent, hubHalfExtent, dirX, dirZ);
  const podEdge = slabEdgeDistance(pod.halfWidth, pod.halfDepth, dirX, dirZ);

  // Overlap both ends so the walkway disappears under each platform instead
  // of butting against it.
  const start = Math.max(0, hubEdge - config.overlap);
  const end = distance - podEdge + config.overlap;
  const length = end - start;
  if (length < config.minLength) return null;
  return { start, end, length, angle: Math.atan2(pod.x, pod.z) };
}

// A Projects pod has no fixed identity the way a Business department does —
// its cluster key is a subagent id, gone once that run ends — so its floor
// colour can never be a deliberate human choice the way a department's is.
// It still gets one: a fixed palette, picked deterministically from the
// cluster's own key, so the SAME pod keeps the SAME colour for its whole
// life (stable across every re-layout as the run continues) while different
// concurrent pods read as different rooms. Distinct hues from the Business
// palette are not required — the two outlets are never on screen together —
// but kept in the same muted family so a Business habit ("the colour is the
// room") carries over.
const PROJECTS_POD_PALETTE = [
  '#e0527d', '#4fae5e', '#e0a934', '#9457c7',
  '#2f9e8f', '#3f7fd4', '#d97a3f', '#3fb0a8',
];

/** Deterministic string hash (not cryptographic — a stable, well-spread
 * index into a small palette is all this needs). */
export function colorForProjectsCluster(cluster) {
  const key = String(cluster || '');
  let hash = 0;
  for (let i = 0; i < key.length; i++) {
    hash = (hash * 31 + key.charCodeAt(i)) | 0;
  }
  const index = Math.abs(hash) % PROJECTS_POD_PALETTE.length;
  return PROJECTS_POD_PALETTE[index];
}

/**
 * Lay the office out.
 *
 * @param {Array<object>} desks adapter desks — `{id, index, workerId, cluster}`
 * @param {object} [options] `seatSpacingX`, `seatSpacingZ`, `podGap`
 * @returns {{pods: Array<object>, seats: Object<string, object>,
 *            center: {x: number, z: number}, radius: number}}
 *   `seats` is keyed by desk id so the scene can look a desk up directly;
 *   `center` and `radius` are what the camera frames with — the middle of the
 *   occupied floor and the distance from it to the outermost pod edge.
 */
export function computeLayout(desks, options) {
  const config = Object.assign({
    seatSpacingX: SEAT_SPACING_X,
    seatSpacingZ: SEAT_SPACING_Z,
    podGap: POD_GAP,
  }, options || {});

  const list = Array.isArray(desks) ? desks : [];

  // Group by cluster, first-seen order. Order is the stability guarantee: a
  // pod keeps its ring slot as long as its cluster keeps existing.
  const byCluster = new Map();
  for (const desk of list) {
    const cluster = desk && desk.cluster ? desk.cluster : '__conductor__';
    if (!byCluster.has(cluster)) byCluster.set(cluster, []);
    byCluster.get(cluster).push(desk);
  }

  // Size every pod before placing any of them: a ring's radius depends on how
  // wide its own pods are.
  const clusters = Array.from(byCluster.entries());
  const sizes = clusters.map(([, seats]) => podSize(seats.length));

  // Widest pod *per ring*, not across the whole office. One large pod used to
  // push every ring outward, leaving small pods marooned in empty floor.
  const extentByRing = new Map();
  sizes.forEach((size, podIndex) => {
    const { ring } = ringSlot(podIndex);
    const extent = Math.max(size.width, size.depth);
    extentByRing.set(ring, Math.max(extentByRing.get(ring) || 0, extent));
  });
  const extentOf = ring => extentByRing.get(ring) || 0;

  // Ring radii, computed once so every pod on a ring shares one. A ring has
  // to clear two things: the ring inside it, and its own neighbours around
  // the circle. Taking only the first leaves the office a small island in a
  // large empty floor; taking only the second lets adjacent rings collide.
  const ringRadii = [CONDUCTOR_RADIUS];
  function radiusForRing(ring) {
    for (let r = ringRadii.length; r <= ring; r += 1) {
      const capacity = RING_BASE_CAPACITY * r;
      // Clearance from whatever is immediately inside: the conductor's pod is
      // a radius, an inner ring of pods reaches out by half its own extent.
      const inward = r === 1
        ? CONDUCTOR_RADIUS + extentOf(1) / 2 + config.podGap
        : ringRadii[r - 1] + extentOf(r - 1) / 2 + extentOf(r) / 2 + config.podGap;
      // Chord clearance between neighbours on this ring.
      const around = (extentOf(r) + config.podGap) / (2 * Math.sin(Math.PI / capacity));
      ringRadii.push(Math.max(inward, around));
    }
    return ringRadii[ring];
  }

  const pods = [];
  const seats = {};

  clusters.forEach(([cluster, clusterDesks], podIndex) => {
    const { ring, indexInRing, capacity } = ringSlot(podIndex);
    const size = sizes[podIndex];
    const ringRadius = radiusForRing(ring);
    // Odd rings start at angle 0, even rings are offset half a slot, so pods
    // on adjacent rings do not line up into radial corridors.
    const offset = (ring % 2 === 0) ? Math.PI / capacity : 0;
    const angle = (2 * Math.PI * indexInRing) / capacity + offset;
    const x = Math.cos(angle) * ringRadius;
    const z = Math.sin(angle) * ringRadius;

    // A Business desk always carries clusterColor explicitly -- a real
    // colour for a department, or a deliberate `null` for "The Floor"
    // overflow (roster.js's businessView sets it either way). A Projects
    // desk never carries the key at all. That distinction, not "is it
    // falsy", is what decides whether this pod gets a colour: an overflow
    // pod's explicit null must stay uncoloured, while a Projects pod (no
    // signal either way) gets one derived from its own cluster key.
    const explicitColorDesk = clusterDesks.find(d => Object.prototype.hasOwnProperty.call(d, 'clusterColor'));
    const { cols, rows } = podGrid(clusterDesks.length);
    const pod = {
      cluster, ring, indexInRing, angle,
      // Present only when the desks carry one (the Business outlet); the
      // scene paints it on the pod floor and skips the sign without it.
      label: (clusterDesks[0] && clusterDesks[0].clusterLabel) || '',
      color: explicitColorDesk ? (explicitColorDesk.clusterColor || null) : colorForProjectsCluster(cluster),
      // Signage glyph next to the name -- Business departments only; a
      // Projects pod has no department to draw an icon for, same as its
      // label, so it is simply absent (no derived fallback the way colour
      // gets one).
      icon: (clusterDesks[0] && clusterDesks[0].clusterIcon) || null,
      x, z,
      width: size.width, depth: size.depth,
      seats: [],
    };

    clusterDesks.forEach((desk, seatIndex) => {
      const col = seatIndex % cols;
      const row = Math.floor(seatIndex / cols);
      // Centre the grid on the pod so a pod of one desk is not lopsided.
      const seat = {
        deskId: desk.id,
        workerId: desk.workerId || null,
        cluster,
        x: x + (col - (cols - 1) / 2) * config.seatSpacingX,
        z: z + (row - (rows - 1) / 2) * config.seatSpacingZ,
        // Desks face the conductor, so a worker seen from the camera is
        // working "into" the middle of the office rather than off the edge.
        rotationY: Math.atan2(x, z) + Math.PI,
      };
      pod.seats.push(seat);
      seats[desk.id] = seat;
    });

    pods.push(pod);
  });

  // Camera framing. A part-filled ring is lopsided — two pods out of six sit
  // on one side of the conductor — so the camera should look at the middle of
  // what actually exists, not at the origin, or the office drifts into a
  // corner with dead floor opposite it.
  const points = [{ x: 0, z: 0, reach: CONDUCTOR_RADIUS }].concat(
    pods.map(pod => ({
      x: pod.x, z: pod.z, reach: Math.max(pod.width, pod.depth) / 2,
    })),
  );
  // Weighted by reach: a fifteen-desk pod is more of the office than a
  // one-desk pod, and an unweighted mean leaves the busy half off-frame.
  const weight = points.reduce((sum, p) => sum + p.reach, 0) || 1;
  const center = {
    x: points.reduce((sum, p) => sum + p.x * p.reach, 0) / weight,
    z: points.reduce((sum, p) => sum + p.z * p.reach, 0) / weight,
  };
  const radius = points.reduce((max, p) => Math.max(
    max, Math.hypot(p.x - center.x, p.z - center.z) + p.reach,
  ), 0);

  return { pods, seats, center, radius };
}
