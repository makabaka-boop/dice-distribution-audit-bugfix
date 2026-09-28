import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// During local dev/preview the UI calls /api/* on its own origin; Vite
// proxies it to the Flask container/service.  In Docker, nginx does the
// same proxying, so application code never hardcodes a host:port.
export default defineConfig({
  plugins: [svelte()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': 'http://localhost:5000',
      '/health': 'http://localhost:5000'
    }
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
    proxy: {
      '/api': 'http://localhost:5000',
      '/health': 'http://localhost:5000'
    }
  }
});
