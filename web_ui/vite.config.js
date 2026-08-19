import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
const backendUrl = process.env.PPT_SYSTEM_API_URL || 'http://127.0.0.1:7860'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: backendUrl,
        changeOrigin: true
      },
      '/output': {
        target: backendUrl,
        changeOrigin: true
      },
      '/runs': {
        target: backendUrl,
        changeOrigin: true
      }
    }
  }
})
