# Libraries.dev (vendored)

Pre-built browser ES modules of Jakub Antalik's Libraries.dev UI effects
(https://github.com/Jakubantalik/Libraries.dev, MIT), built from the sources in
`tools/libraries-dev/vendor-src/` by `tools/libraries-dev/build.mjs`. The folder
name is the upstream commit.

- `libraries-dev.js`: BorderBeam, ThinkingOrb, BotAvatar, Liquid (+ LiquidItem),
  VoiceBeam, MetalFx, MetalText, MetalBadge, and `mount()`.
- `img-fx.js`: ImageGeneration (imports three.js from `static/vendor/three`).
- `chunks/`: the shared React 19 runtime.

Use from plain JS (loaded on demand, never on every page):

```js
const lib = await window.loadLibrariesDev();        // static/libraries-dev.js
const handle = lib.mount(element, 'ThinkingOrb', { state: 'thinking' });
handle.update({ state: 'writing' });
handle.unmount();
```

Read `tools/libraries-dev/skill-reference/` (the author's usage guide) for each
component's props and where it fits. Licences: `LICENSE-*.txt` here.
