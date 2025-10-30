import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'

const certPath = process.env.SSL_CERT_PATH || path.join(__dirname, 'ssl', 'cert.pem')
const keyPath = process.env.SSL_KEY_PATH || path.join(__dirname, 'ssl', 'key.pem')

// Backend URL - use localhost by default, but allow override via env var
// For external access, set VITE_BACKEND_URL to http://YOUR_IP:5000
const backendUrl = process.env.VITE_BACKEND_URL || 'http://localhost:5000'

let httpsConfig = false
if (fs.existsSync(certPath) && fs.existsSync(keyPath)) {
  httpsConfig = {
    cert: fs.readFileSync(certPath),
    key: fs.readFileSync(keyPath)
  }
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    https: httpsConfig,
    strictPort: true,
    proxy: {
      '/api': {
        target: backendUrl,
        changeOrigin: true,
        secure: false,
        ws: false,
      },
      '/auth': {
        target: backendUrl,
        changeOrigin: true,
        secure: false,
        ws: false,
      },
      '/socket.io': {
        target: backendUrl,
        changeOrigin: true,
        ws: true,
        secure: false,
      }
    }
  }
})

