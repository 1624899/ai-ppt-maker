import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 7862,
    proxy: {
      '/api': { target: 'http://127.0.0.1:7860', changeOrigin: true },
      '/runs': { target: 'http://127.0.0.1:7860', changeOrigin: true },
      '/output': { target: 'http://127.0.0.1:7860', changeOrigin: true }
    }
  }
});
