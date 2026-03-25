// Vite config for the standalone archml-export single-file HTML build.
// Produces archml-viewer-template.html with all JS and CSS inlined.
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [viteSingleFile()],
  build: {
    rollupOptions: {
      input: resolve(__dirname, "index.html"),
    },
    outDir: resolve(__dirname, "../../static"),
    emptyOutDir: false,
  },
});
