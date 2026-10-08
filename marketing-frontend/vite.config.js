import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// The API proxy goes to 127.0.0.1: on Windows "localhost" is tried as IPv6 first (about 2 s per connection).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: { '/api': { target: 'http://127.0.0.1:8001', changeOrigin: true } }
  }
})
