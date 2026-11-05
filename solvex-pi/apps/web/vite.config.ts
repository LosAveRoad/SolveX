import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { readdirSync, readFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const katexFonts = join(dirname(require.resolve('katex/package.json', { paths: [dirname(require.resolve('@mariozechner/mini-lit/dist/index.js'))] })), 'dist/fonts');
export default defineConfig({
  root: fileURLToPath(new URL('./client/', import.meta.url)),
  base: '/ui/',
  plugins: [{
    name: 'pi-katex-fonts',
    generateBundle() {
      // Pi's prebuilt CSS references fonts/ relative to the emitted stylesheet.
      for (const name of readdirSync(katexFonts)) this.emitFile({type:'asset', fileName:`assets/fonts/${name}`, source:readFileSync(join(katexFonts,name))});
    },
  }],
  build: { outDir: '../dist', emptyOutDir: true, target: 'es2022' },
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
});
