import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api/v2': {
        target: 'https://chuyenchochung.com',
        changeOrigin: true,
        secure: true,
      },
    },
  },
})
