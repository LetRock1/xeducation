import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// host: true -> the website is also reachable from a phone on the same Wi-Fi (http://<laptop-ip>:5173), so the
// "View Course" button in an email opened on the phone works when PUBLIC_SITE_URL is set to that address.
// The API proxy goes to 127.0.0.1: on Windows "localhost" is tried as IPv6 first (about 2 s per connection).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } }
  }
})
