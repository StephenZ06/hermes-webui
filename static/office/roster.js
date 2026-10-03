// Business outlet — a departmental floor plan over the same live state.
//
// The Projects outlet draws exactly what `delegate_task` did: a desk per
// subagent, pods by parent. Business draws the same run as a company — six
// standing departments whose desks are named before anyone sits at them, so
// an idle office still reads as an organisation rather than an empty room.
//
// Both outlets consume identical adapter state. The only difference is desk
// assignment policy, which is what this module is: it returns a desk list in
// exactly the shape the adapter produces, so `computeLayout` and the scene
// need no idea which outlet is showing.
//
// What this is NOT: a second orchestrator. No agent here can be "run". Hermes
// decides what to delegate and to whom; a department is a place to sit the
// subagents it actually spawned.
//
// Standing caveat: hermes-webui has no department-scoped agent library yet —
// `/api/personalities` returns names and descriptions only (see
// api/routes.py's /api/personalities). Departments are therefore inferred
// from the persona's own words, and anything that matches nothing lands on
// the floor rather than being forced into a department it does not belong to.
// When a real agent library lands, `buildRoster` reads its department field
// and the keyword pass below goes away. See docs/HERMES_STUDIO_PARITY_PLAN.md.
//
// Pure: no DOM, no fetch, no three.js, so tests/test_office_roster.py runs it
// under node.

/**
 * The standing departments, in floor order. Order is fixed so a department
 * keeps its place on the floor whatever the roster holds — an office whose
 * rooms move when someone is hired is not an office.
 */
export const DEPARTMENTS = [
  {
    key: 'marketing', name: 'Marketing', color: '#ec4899',
    keywords: ['marketing', 'content', 'brand', 'campaign', 'social', 'newsletter',
      'ads', 'ad ', 'seo', 'copy', 'blog', 'video', 'design', 'graphic'],
  },
  {
    key: 'emails', name: 'Emails', color: '#10b981',
    keywords: ['email', 'inbox', 'mail', 'reply', 'correspondence', 'outreach',
      'follow up', 'follow-up'],
  },
  {
    key: 'sales', name: 'Sales', color: '#f59e0b',
    keywords: ['sales', 'lead', 'prospect', 'pipeline', 'deal', 'proposal',
      'quote', 'crm', 'customer'],
  },
  {
    key: 'operations', name: 'Operations', color: '#8b5cf6',
    keywords: ['operation', 'ops', 'process', 'compliance', 'legal', 'policy',
      'admin', 'intel', 'research', 'report', 'dashboard'],
  },
  {
    key: 'finance', name: 'Finance', color: '#06b6d4',
    keywords: ['finance', 'invoice', 'billing', 'payment', 'account', 'budget',
      'payroll', 'cost', 'reconcil', 'tax'],
  },
  {
    key: 'delivery', name: 'Delivery', color: '#3b82f6',
    keywords: ['delivery', 'deliver', 'qa', 'quality', 'test', 'onboard',
      'support', 'ship', 'release'],
  },
];

/**
 * The permanent Projects Office workstreams. Unlike a temporary parent-agent
 * cluster, these represent the kind of work being delegated, so their names,
 * colour and floor position remain recognisable before anyone is seated.
 */
export const PROJECT_FLOORS = [
  { key: 'general', name: 'General', color: '#94a3b8' },
  { key: 'research', name: 'Research', color: '#8b5cf6' },
  { key: 'coding', name: 'Coding', color: '#3b82f6' },
  { key: 'documents', name: 'Documents', color: '#14b8a6' },
];

const PROJECT_FLOOR_BY_KEY = new Map(PROJECT_FLOORS.map(floor => [floor.key, floor]));

const PROJECT_RESEARCH_KEYWORDS = [
  'research', 'investigat', 'source comparison', 'literature', 'discovery',
  'fact finding', 'fact-finding', 'analyse', 'analyze', 'analysis',
];
const PROJECT_DOCUMENT_KEYWORDS = [
  'document', ' pdf', 'spreadsheet', 'slide', 'presentation', 'template',
  'format', 'convert', 'word file', 'docx',
];

/**
 * Where a subagent goes when nothing matches. A visible overflow is the
 * honest answer: forcing an unrecognised worker into a department would make
 * the floor plan lie about what Hermes is doing.
 */
export const OVERFLOW = { key: 'floor', name: 'The Floor' };

const DEPARTMENT_BY_KEY = new Map(DEPARTMENTS.map(d => [d.key, d]));

/**
 * A department's floor accent colour, or null for a cluster that names no
 * department (the Projects outlet, "Subagents", "The Floor" overflow) — those
 * keep the palette's plain, uncoloured pod so only Business floors read as a
 * company with distinct rooms.
 */
export function colorForDepartment(clusterKey) {
  const dept = DEPARTMENT_BY_KEY.get(clusterKey);
  return dept ? dept.color : null;
}

function normalise(text) {
  return String(text == null ? '' : text).toLowerCase().replace(/[_\-/]+/g, ' ');
}

// Concrete engineering signals take priority over the broad wording shared
// by personal and business work. Vague words such as "build" and "project"
// are intentionally absent: they cannot reliably choose an office alone.
const CODING_KEYWORDS = [
  'code', 'coding', 'software', 'program', 'repository', ' repo ', 'commit',
  'pull request', 'frontend', 'backend', 'api', 'database', 'react',
  'javascript', 'typescript', 'python', 'html', 'css', 'debug', 'refactor',
  'bug', 'unit test', 'test suite', 'regression test', 'web app', 'website',
  'deploy', 'implementation', 'implement', 'fix ',
];

// A business task can be valid without naming one of the six departments. It
// then belongs on The Floor, rather than appearing as a Projects task.
const BUSINESS_CONTEXT_KEYWORDS = [
  'business', 'company', 'client', 'customer', 'vendor', 'stakeholder',
  'offsite', 'meeting', 'strategy', 'roadmap', 'team', 'revenue',
];

/**
 * Best-matching department for a piece of text, or null.
 *
 * Scored rather than first-match: "invoice reminder email" mentions both
 * Finance and Emails, and the department with more evidence should win
 * instead of whichever happens to be declared first.
 */
export function departmentFor(text) {
  const hay = normalise(text);
  if (!hay.trim()) return null;
  let best = null;
  let bestScore = 0;
  for (const dept of DEPARTMENTS) {
    let score = 0;
    for (const keyword of dept.keywords) {
      if (hay.includes(keyword)) score += keyword.length;
    }
    if (score > bestScore) {
      bestScore = score;
      best = dept;
    }
  }
  return best;
}

/** The shared visual-routing guideline for the two Office outlets. */
export function officeFor(text) {
  const hay = normalise(text);
  if (!hay.trim()) return 'projects';
  if (CODING_KEYWORDS.some(keyword => hay.includes(keyword))) return 'projects';
  // Research is a first-class Projects workstream unless the wording also
  // identifies it as company work. This prevents generic investigations from
  // being swept into Business Operations solely because both use the word.
  if (PROJECT_RESEARCH_KEYWORDS.some(keyword => hay.includes(keyword))
    && !BUSINESS_CONTEXT_KEYWORDS.some(keyword => hay.includes(keyword))) return 'projects';
  if (departmentFor(hay)) return 'business';
  if (BUSINESS_CONTEXT_KEYWORDS.some(keyword => hay.includes(keyword))) return 'business';
  return 'projects';
}

/**
 * Classify a direct, non-Business Projects task. This intentionally has a
 * fixed priority: explicit research owns mixed research/coding work, coding
 * owns ordinary implementation, documents owns the remaining document work,
 * and General is the honest fallback for everything else.
 */
export function projectFloorFor(text) {
  const hay = normalise(text);
  if (PROJECT_RESEARCH_KEYWORDS.some(keyword => hay.includes(keyword))) return 'research';
  if (CODING_KEYWORDS.some(keyword => hay.includes(keyword))) return 'coding';
  if (PROJECT_DOCUMENT_KEYWORDS.some(keyword => hay.includes(keyword))) return 'documents';
  return 'general';
}

/**
 * Business-owned worker ids, including descendants of a business root. The
 * fixed-point walk works with replayed events where a child can arrive first.
 */
export function businessWorkerIds(workers) {
  const list = Array.isArray(workers) ? workers : [];
  const business = new Set(list
    .filter(worker => worker && (worker.scheduledTask || officeFor(worker.goal || worker.label || '') === 'business'))
    .map(worker => worker.id)
    .filter(Boolean));
  let changed = true;
  while (changed) {
    changed = false;
    list.forEach(worker => {
      if (worker && worker.id && worker.parentId && business.has(worker.parentId)
        && !business.has(worker.id)) {
        business.add(worker.id);
        changed = true;
      }
    });
  }
  return business;
}

/**
 * Adapter-shaped view for Projects Office. The existing scene and layout see
 * four permanent labelled pods, while real workers take seats on the floor
 * chosen by their root workstream. A child inherits its closest known
 * Projects ancestor so one delegation branch never jumps across floors.
 */
export function projectsView(state) {
  const source = state || {};
  const workers = Array.isArray(source.workers) ? source.workers : [];
  const businessIds = businessWorkerIds(workers);
  const workerById = new Map(workers.filter(worker => worker && worker.id).map(worker => [worker.id, worker]));
  const resolved = new Map();

  const floorForWorker = (worker, trail) => {
    if (!worker || !worker.id) return 'general';
    if (resolved.has(worker.id)) return resolved.get(worker.id);
    const seen = trail || new Set();
    if (seen.has(worker.id)) return projectFloorFor(worker.goal || worker.label || '');
    seen.add(worker.id);
    const parent = worker.parentId ? workerById.get(worker.parentId) : null;
    const floor = parent && !businessIds.has(parent.id)
      ? floorForWorker(parent, seen)
      : projectFloorFor(worker.goal || worker.label || '');
    seen.delete(worker.id);
    resolved.set(worker.id, floor);
    return floor;
  };

  const desks = [];
  const freeSeats = new Map();
  PROJECT_FLOORS.forEach(floor => {
    const desk = {
      id: `seat-project-${floor.key}-lead`, index: desks.length, workerId: null,
      cluster: floor.key, seatLabel: `${floor.name} Lead`,
      clusterLabel: floor.name, clusterColor: floor.color, projectFloor: true,
    };
    desks.push(desk);
    freeSeats.set(floor.key, [desk]);
  });

  const visibleWorkers = workers
    .filter(worker => worker && worker.id && !businessIds.has(worker.id))
    .slice()
    .sort((a, b) => {
      const aLive = a.status === 'running' ? 0 : 1;
      const bLive = b.status === 'running' ? 0 : 1;
      return aLive - bLive || (a.spawnedAt || 0) - (b.spawnedAt || 0);
    });

  visibleWorkers.forEach(worker => {
    const floorKey = floorForWorker(worker);
    const floor = PROJECT_FLOOR_BY_KEY.get(floorKey) || PROJECT_FLOOR_BY_KEY.get('general');
    let desk = (freeSeats.get(floor.key) || []).find(candidate => candidate.workerId === null);
    if (!desk) {
      desk = {
        id: `seat-project-${floor.key}-extra-${worker.id}`, index: desks.length, workerId: null,
        cluster: floor.key, seatLabel: floor.name,
        clusterLabel: floor.name, clusterColor: floor.color, projectFloor: true,
      };
      desks.push(desk);
      freeSeats.get(floor.key).push(desk);
    }
    desk.workerId = worker.id;
  });

  return Object.assign({}, source, { desks });
}

function titleCase(name) {
  return String(name || '')
    .replace(/[_\-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, c => c.toUpperCase());
}

/**
 * Build the standing roster from the app's personas.
 *
 * Every department always exists and always has at least one desk, so the
 * office is a company before it is busy.
 *
 * @param {Array<{name: string, description: string}>} personalities
 * @returns {{departments: Array<object>}}
 */
export function buildRoster(personalities) {
  const list = Array.isArray(personalities) ? personalities : [];
  const seatsByDept = new Map(DEPARTMENTS.map(d => [d.key, []]));
  const overflowSeats = [];

  list.forEach(persona => {
    if (!persona || !persona.name) return;
    const label = titleCase(persona.name);
    // The persona's name carries the intent; its description is supporting
    // evidence, so both are searched but the name is weighted by being read
    // first and scored on its own when it matches anything at all.
    const dept = departmentFor(persona.name)
      || departmentFor(`${persona.name} ${persona.description || ''}`);
    const seat = {
      id: `seat-${dept ? dept.key : OVERFLOW.key}-${persona.name}`,
      department: dept ? dept.key : OVERFLOW.key,
      label,
      persona: persona.name,
      placeholder: false,
    };
    if (dept) seatsByDept.get(dept.key).push(seat);
    else overflowSeats.push(seat);
  });

  const departments = DEPARTMENTS.map(dept => {
    const seats = seatsByDept.get(dept.key);
    if (!seats.length) {
      // A department with no persona still gets its desk, so all six pods
      // stand whatever the config holds.
      seats.push({
        id: `seat-${dept.key}-lead`,
        department: dept.key,
        label: `${dept.name} Lead`,
        persona: null,
        placeholder: true,
      });
    }
    return { key: dept.key, name: dept.name, color: dept.color, seats };
  });

  // Keep The Floor as a real room even when no task currently overflows into
  // it. This guarantees its platform is rendered with the same four-layer
  // stack as every department instead of disappearing when it is empty.
  if (!overflowSeats.length) {
    overflowSeats.push({
      id: `seat-${OVERFLOW.key}-lead`,
      department: OVERFLOW.key,
      label: OVERFLOW.name,
      persona: null,
      placeholder: true,
    });
  }
  departments.push({ key: OVERFLOW.key, name: OVERFLOW.name, seats: overflowSeats });
  return { departments };
}

/**
 * Seat the live workers on the departmental floor.
 *
 * Returns adapter-shaped state: identical to what `getState()` produces
 * except that `desks` are roster seats rather than allocation order. The
 * scene and the layout therefore need no idea which outlet is showing.
 *
 * @param {object} state adapter state
 * @param {object} roster from `buildRoster`
 */
export function businessView(state, roster) {
  const source = state || {};
  const workers = Array.isArray(source.workers) ? source.workers : [];
  const businessIds = businessWorkerIds(workers);
  const departments = (roster && roster.departments) ? roster.departments : buildRoster([]).departments;

  // Seats in floor order, each still free.
  const desks = [];
  const seatIndexByDept = new Map();
  departments.forEach(dept => {
    seatIndexByDept.set(dept.key, []);
    dept.seats.forEach(seat => {
      const desk = {
        id: seat.id,
        index: desks.length,
        workerId: null,
        cluster: dept.key,
        seatLabel: seat.label,
        // Painted on the floor of the pod. Only Business has names worth
        // painting; a Projects cluster is a parent subagent id, which means
        // nothing to a reader.
        clusterLabel: dept.name,
        // Tints the pod floor (see layout.js's computeLayout and builders
        // .js's makePod). A real department gets its declared colour; "The
        // Floor" overflow gets an explicit `null` -- present and deliberate,
        // not merely absent -- so computeLayout can tell "no colour, on
        // purpose" apart from a Projects desk, which never carries this key
        // at all and gets one derived instead.
        clusterColor: dept.key === OVERFLOW.key ? null : dept.color,
      };
      seatIndexByDept.get(dept.key).push(desk);
      desks.push(desk);
    });
  });

  const takeFreeSeat = deptKey => {
    const seats = seatIndexByDept.get(deptKey);
    if (!seats) return null;
    return seats.find(desk => desk.workerId === null) || null;
  };

  // Running workers are seated first so a busy department shows its live work
  // rather than whichever subagent happened to spawn first.
  const ordered = workers.filter(worker => businessIds.has(worker.id)).sort((a, b) => {
    const aLive = a.status === 'running' ? 0 : 1;
    const bLive = b.status === 'running' ? 0 : 1;
    if (aLive !== bLive) return aLive - bLive;
    return (a.spawnedAt || 0) - (b.spawnedAt || 0);
  });

  ordered.forEach(worker => {
    // Scheduler work is intentionally shown on THE FLOOR. Its name is not a
    // department assignment, even when it happens to contain one.
    const dept = worker.scheduledTask ? null : departmentFor(worker.goal || worker.label || '');
    let desk = dept ? takeFreeSeat(dept.key) : null;
    if (!desk) desk = takeFreeSeat(OVERFLOW.key);
    if (!desk) {
      // Every seat in the department and on the floor is taken: add another
      // floor desk rather than dropping a worker Hermes really is running.
      desk = {
        id: `seat-${OVERFLOW.key}-extra-${worker.id}`,
        index: desks.length,
        workerId: null,
        cluster: OVERFLOW.key,
        seatLabel: OVERFLOW.name,
        clusterLabel: OVERFLOW.name,
        clusterColor: null,
      };
      seatIndexByDept.get(OVERFLOW.key).push(desk);
      desks.push(desk);
    }
    desk.workerId = worker.id;
  });

  return Object.assign({}, source, { desks });
}

/** Display name for a department key, for the panel's own chrome. */
export function departmentName(key) {
  if (key === OVERFLOW.key) return OVERFLOW.name;
  const dept = DEPARTMENT_BY_KEY.get(key);
  return dept ? dept.name : key;
}
