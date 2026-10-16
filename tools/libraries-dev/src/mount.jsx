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
  const render = () => root.render(React.createElement(Component, withAdopted(current)));
  render();
  const handle = {
    update(next) { current = { ...current, ...next }; render(); },
    unmount() { root.unmount(); if (element.__librariesDevRoot === handle) delete element.__librariesDevRoot; },
  };
  element.__librariesDevRoot = handle;
  return handle;
}

// ``adopt``: an existing DOM node to show as the component's child (so a
// wrapper such as BorderBeam can go around content the app already drew).
function withAdopted(props) {
  if (!props || !props.adopt) return props;
  const { adopt, ...rest } = props;
  const slot = React.createElement('div', {
    style: { display: 'contents' },
    ref: (node) => { if (node && adopt.parentNode !== node) node.appendChild(adopt); },
  });
  return { ...rest, children: slot };
}

/* Wrap ``element`` (already in the page) with component ``name``: a host takes
   its place and the component renders around it. unmount() puts it back. */
export function wrap(element, name, props = {}) {
  const host = document.createElement('div');
  host.className = 'libdev-host';
  element.replaceWith(host);
  const handle = mount(host, name, { ...props, adopt: element });
  const unmount = handle.unmount;
  handle.unmount = () => { unmount(); host.replaceWith(element); };
  return handle;
}

export { React };
