import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss()
  ],

  server: {
    host: '0.0.0.0',           // Keep your existing setting
    port: 8081,                 // ← Changed to match ngrok
    strictPort: true,           // Prevent fallback to random port
    cors: true,

    // ← THIS FIXES THE "Blocked request" ERROR
    allowedHosts: [
      'dry-handcraft-dusk.ngrok-free.dev',   // Your exact domain
      '.ngrok-free.dev',                     // Allows ALL ngrok domains
      'localhost',
      '127.0.0.1'
    ]
  },

  preview: {
    host: '0.0.0.0',
    port: 8081
  },

  build: {
    commonjsOptions: {
      transformMixedEsModules: true
    }
  }
})