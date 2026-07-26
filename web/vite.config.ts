import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// GitHub project Pages serves under /<repo>/ — set GITHUB_PAGES=true in CI.
const base = process.env.GITHUB_PAGES === 'true' ? '/tax-receipt-prototype/' : '/'

export default defineConfig({
  base,
  plugins: [react()],
  test: {
    environment: 'node',
  },
})
