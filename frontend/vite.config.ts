import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss()
  ],
  server: {
    host: '0.0.0.0',  // Allow local network access
    port: 5173,        // Use Vite's default port to avoid conflicts
    strictPort: false,  // Allow fallback if port is taken
    cors: true,
  },
  preview: {
    host: '0.0.0.0',
    port: 5173
  },
  build: {
    commonjsOptions: {
      transformMixedEsModules: true
    }
  }
})
