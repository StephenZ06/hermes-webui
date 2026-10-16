// Shared React runtime + a tiny bridge so the vanilla-JS app can place a
// Libraries.dev component in any element: LibrariesDev.mount(el, 'BorderBeam', props).
import React from 'react';
import { createRoot } from 'react-dom/client';

const registry = {};

export function register(components) {
  Object.assign(registry, components);
}

/* Render ``name`` into ``element`` with ``props``. Returns a handle:
   update(nextProps) re-renders, unmount() removes it and frees the root.
   ``children`` may be a string of plain text (no HTML). */
export function mount(element, name, props = {}) {
  const Component = registry[name];
  if (!Component) throw new Error(`Unknown Libraries.dev component: ${name}`);
  if (!element) throw new Error('LibrariesDev.mount needs an element');
  if (element.__librariesDevRoot) element.__librariesDevRoot.unmount();
  const root = createRoot(element);
  let current = props;
  const render = () => root.render(React.createElement(Component, current));
  render();
  const handle = {
    update(next) { current = { ...current, ...next }; render(); },
    unmount() { root.unmount(); if (element.__librariesDevRoot === handle) delete element.__librariesDevRoot; },
  };
  element.__librariesDevRoot = handle;
  return handle;
}

export { React };
