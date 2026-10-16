/* Pixel warlock for the Character page. One 20x24 drawing, re-coloured and
   given more gear at each tier (Apprentice, Adept, Sorcerer, Archmage,
   Legendary). Drawn as box-shadows on one element, so it stays crisp at any
   size and needs no image files. */
(() => {
  'use strict';
  // . empty  h hood  H hood light  s skin  e eye  r robe dark  R robe  t trim
  // w staff  o orb  O orb core  b boots  c crown  m mouth/shadow
  const BASE = [
    '........hh..........',
    '.......hHHh.........',
    '......hHHHHh........',
    '.....hHHHHHHh.......',
    '....hhHHHHHHhh......',
    '....hhssssssh.......',
    '.....sesssesh...o...',
    '.....ssssssss..oOo..',
    '.....smmmmmms...o...',
    '....rrRRRRRRrr..w...',
    '...rRRRRRRRRRRr.w...',
    '..rRRRRttRRRRRRrw...',
    '..rRR.RttRR.RRrsw...',
    '..ss..RttRR..ss.w...',
    '......RRRRR.....w...',
    '.....rRRRRRr....w...',
    '.....rRRRRRr....w...',
    '....rRRRRRRRr...w...',
    '....rRRRRRRRr...w...',
    '...rRRRRRRRRRr..w...',
    '...rRRR...RRRr......',
    '....bb.....bb.......',
    '...bbb.....bbb......',
    '....................',
  ];
  const TIERS = [
    {name: 'Apprentice', h: '#5b4636', H: '#7a604a', r: '#3d3a33', R: '#5f5a50', t: '#5f5a50', w: '#7a5230', o: null, O: null, b: '#2b241d'},
    {name: 'Adept', h: '#2c4a7a', H: '#3f66a6', r: '#1e3358', R: '#2f5190', t: '#9fb7d9', w: '#7a5230', o: '#7fd3ff', O: '#e8f8ff', b: '#1b2333'},
    {name: 'Sorcerer', h: '#4a2a7a', H: '#6b44a6', r: '#2e1a52', R: '#5b3a9a', t: '#ffd60a', w: '#5b3a22', o: '#c084fc', O: '#fff1ff', b: '#1d1430'},
    {name: 'Archmage', h: '#35155f', H: '#5d2aa0', r: '#1f0c3d', R: '#4a1f86', t: '#ffd60a', w: '#d4a017', o: '#a855f7', O: '#ffffff', b: '#140a26', c: '#ffd60a'},
    {name: 'Legendary', h: '#1a1a1a', H: '#2d2d2d', r: '#0d0d0d', R: '#262626', t: '#ffd60a', w: '#ffd60a', o: '#ff7a1a', O: '#fff4c2', b: '#0a0a0a', c: '#ffd60a'},
  ];
  const SKIN = {s: '#f1c9a0', e: '#ffffff', m: '#d9a982'};

  function grid(tier) {
    const rows = BASE.map((row) => row.split(''));
    const t = TIERS[tier - 1];
    if (!t.o) { // no orb yet: a plain walking stick
      [[16, 6], [15, 7], [17, 7], [16, 8]].forEach(([x, y]) => { rows[y][x] = '.'; });
      rows[7][16] = 'w'; rows[8][16] = 'w';
    }
    if (tier >= 3) { rows[6][6] = 'o'; rows[6][10] = 'o'; } // eyes glow with power
    if (tier >= 4) { // crown points above the hood
      [[7, 0], [9, 0], [11, 0]].forEach(([x, y]) => { rows[y][x] = 'c'; });
      [[15, 5], [17, 5]].forEach(([x, y]) => { rows[y][x] = 'o'; }); // bigger orb
    }
    if (tier >= 5) { // a mantle and gilded boots
      for (const y of [10, 11, 12]) { rows[y][1] = 't'; }
      rows[21][4] = 't'; rows[21][12] = 't';
    }
    return rows;
  }

  function shadows(tier, scale) {
    const t = TIERS[Math.max(1, Math.min(5, tier)) - 1];
    const palette = {...SKIN, ...t};
    const out = [];
    grid(tier).forEach((row, y) => row.forEach((code, x) => {
      const colour = palette[code];
      if (code !== '.' && colour) out.push(`${x * scale}px ${y * scale}px 0 0 ${colour}`);
    }));
    return out.join(',');
  }

  /* Markup for the sprite at a tier. ``scale`` is the size of one pixel. */
  function render(tier, scale = 8) {
    const t = Math.max(1, Math.min(5, tier || 1));
    return `<span class="px-hero" data-tier="${t}" style="--px:${scale}px;width:${20 * scale}px;height:${24 * scale}px" role="img" aria-label="${TIERS[t - 1].name} warlock">
      <span class="px-hero-art" style="width:${scale}px;height:${scale}px;box-shadow:${shadows(t, scale)}"></span>
    </span>`;
  }

  window.DashSprite = {render, tiers: TIERS.map((t) => t.name)};
})();
