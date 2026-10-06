// Build the vendored BlockNote bundle for the Notes page.
//   cd tools/blocknote && npm ci && npm run build
// Output: static/vendor/blocknote/<version>/blocknote-hermes.{js,css}
import { build } from "esbuild";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const version = JSON.parse(readFileSync(resolve(here, "node_modules/@blocknote/core/package.json"), "utf8")).version;
const outdir = resolve(here, "../../static/vendor/blocknote", version);
mkdirSync(outdir, { recursive: true });

await build({
  entryPoints: { "blocknote-hermes": resolve(here, "src/entry.jsx") },
  outdir,
  bundle: true,
  format: "esm",
  platform: "browser",
  target: ["es2020"],
  jsx: "automatic",
  minify: true,
  legalComments: "linked",
  define: { "process.env.NODE_ENV": '"production"' },
  loader: { ".woff": "file", ".woff2": "file", ".svg": "dataurl" },
  // CSS @import of package subpaths: esbuild's CSS resolver does not apply
  // the packages' "style" export condition, so point at the files directly.
  alias: {
    "@blocknote/react/style.css": resolve(here, "node_modules/@blocknote/react/dist/style.css"),
    "@blocknote/core/style.css": resolve(here, "node_modules/@blocknote/core/dist/style.css"),
  },
  logLevel: "info",
});

writeFileSync(
  resolve(outdir, "README.md"),
  `# BlockNote ${version} (vendored)\n\nBuilt by \`tools/blocknote\` (\`npm ci && npm run build\`).\n` +
    `Packages: @blocknote/core, @blocknote/react, @blocknote/mantine (MPL-2.0), React and Mantine (MIT).\n` +
    `No GPL \`@blocknote/xl-*\` packages are included. Third-party licence texts: blocknote-hermes.js.LEGAL.txt.\n`,
);
