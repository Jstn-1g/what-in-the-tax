import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: '/',
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5401,
    strictPort: true,
  },
  preview: {
    host: '127.0.0.1',
    port: 5402,
    strictPort: true,
  },
  test: {
    environment: 'node',
  },
})
