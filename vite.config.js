import { defineConfig } from 'vite'

// Relative base so the same build works on GitHub Pages project subpaths
// (https://evolvedhow.github.io/fdga-xray/), on Modal, and from file://-style
// static hosts. All asset references use import.meta.env.BASE_URL.
export default defineConfig({
  base: './',
  publicDir: 'public',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    assetsInlineLimit: 4096,
  },
})
