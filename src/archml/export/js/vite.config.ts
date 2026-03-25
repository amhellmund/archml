// Vite config for the Sphinx / per-page JS+CSS build.
// Produces archml-viewer.js (IIFE) and archml-diagram.css in src/archml/static/.
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { defineConfig } from "vite";

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  build: {
    rollupOptions: {
      input: resolve(__dirname, "src/main.ts"),
      output: {
        format: "iife",
        name: "ArchMLViewer",
        entryFileNames: "archml-viewer.js",
        assetFileNames: "archml-diagram[extname]",
      },
    },
    outDir: resolve(__dirname, "../../static"),
    emptyOutDir: false,
  },
});
