import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/layout': 'http://127.0.0.1:8000',
      '/video': 'http://127.0.0.1:8000',
      '/metadata': 'http://127.0.0.1:8000',
      '/frame': 'http://127.0.0.1:8000',
      '/explain': 'http://127.0.0.1:8000',
      '/associate': 'http://127.0.0.1:8000',
      '/fps': 'http://127.0.0.1:8000'
    }
  }
})
