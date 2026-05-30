import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:7860',
        changeOrigin: true
      },
      '/output': {
        target: 'http://127.0.0.1:7860',
        changeOrigin: true
      }
    }
  }
})
