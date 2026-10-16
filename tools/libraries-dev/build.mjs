// Builds static/vendor/libraries-dev/<version>/ from the vendored Libraries.dev
// sources (vendor-src/, MIT; paper-design shaders Apache-2.0). Not part of the
// app at runtime: the app loads the committed, pre-built ES modules.
//
// React 19 and esbuild come from ../blocknote/node_modules (the Notes editor
// bundle's toolchain), so nothing is installed here. Run: node build.mjs
// (LIBDEV_NODE_MODULES=/path/to/node_modules overrides, e.g. from a worktree).
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';

const here = path.dirname(fileURLToPath(import.meta.url));
const VERSION = 'bfcb863'; // Jakubantalik/Libraries.dev commit the sources were copied from
const out = path.resolve(here, '../../static/vendor/libraries-dev', VERSION);
const modules = path.resolve(process.env.LIBDEV_NODE_MODULES || path.join(here, '../blocknote/node_modules'));
const { build } = await import(path.join(modules, 'esbuild/lib/main.js'));
const pkg = (name) => path.join(here, 'vendor-src', name, 'src', 'index.ts');
const THREE_URL = '/static/vendor/three/0.185.1/three.module.min.js';

const aliases = {
  'border-beam': pkg('border-beam'),
  'thinking-orbs/engine': path.join(here, 'vendor-src/thinking-orbs/src/engine/index.ts'),
  'thinking-orbs': pkg('thinking-orbs'),
  'bot-avatars': pkg('bot-avatars'),
  'liquid-gooey': pkg('liquid-gooey'),
  'voice-glow': pkg('voice-glow'),
  'metal-fx': pkg('metal-fx'),
  'img-fx': pkg('img-fx'),
  '@paper-design/shaders': path.join(here, 'vendor-src/paper-design-shaders/src/shaders/liquid-metal.ts'),
};

const resolver = {
  name: 'libraries-dev-resolve',
  setup(b) {
    b.onResolve({ filter: /^three$/ }, () => ({ path: THREE_URL, external: true }));
    b.onResolve({ filter: /^(border-beam|thinking-orbs(\/engine)?|bot-avatars|liquid-gooey|voice-glow|metal-fx|img-fx|@paper-design\/shaders)$/ },
      (args) => ({ path: aliases[args.path] }));
  },
};

fs.rmSync(out, { recursive: true, force: true });
await build({
  entryPoints: { 'libraries-dev': path.join(here, 'src/core.jsx'), 'img-fx': path.join(here, 'src/img-fx.jsx') },
  outdir: out,
  bundle: true,
  splitting: true,
  format: 'esm',
  minify: true,
  target: ['es2020'],
  jsx: 'automatic',
  nodePaths: [modules],
  plugins: [resolver],
  define: {
    'process.env.NODE_ENV': '"production"',
    __VOICE_SURFACE__: 'false',
    __LIBDEV_VERSION__: JSON.stringify(VERSION),
  },
  chunkNames: 'chunks/[name]-[hash]',
  legalComments: 'linked',
  logLevel: 'info',
});
for (const name of fs.readdirSync(path.join(here, 'vendor-src'))) {
  const license = fs.readdirSync(path.join(here, 'vendor-src', name)).find((f) => f.startsWith('LICENSE'));
  if (license) fs.copyFileSync(path.join(here, 'vendor-src', name, license), path.join(out, `LICENSE-${name}.txt`));
}
console.log('built', out);
