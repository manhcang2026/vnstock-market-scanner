import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ command, mode }) => {
  if (command !== 'serve') return { plugins: [react()] }

  const env = loadEnv(mode, process.cwd(), 'CCC_DEV_')
  const apiTarget = env.CCC_DEV_API_TARGET?.trim()
  const wsTarget = env.CCC_DEV_WS_TARGET?.trim()
  if (!apiTarget || !wsTarget) {
    throw new Error('Local dev requires CCC_DEV_API_TARGET and CCC_DEV_WS_TARGET in website-v2-react/.env.local')
  }

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api/v2/live': {
          target: wsTarget,
          ws: true,
          changeOrigin: true,
        },
        '/api/v2': {
          target: apiTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/v2\//, '/v1/'),
        },
      },
    },
  }
})
