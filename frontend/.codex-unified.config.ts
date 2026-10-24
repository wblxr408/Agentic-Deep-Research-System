import { defineConfig, mergeConfig } from 'vite'
import base from './vite.config'
export default mergeConfig(base, defineConfig({ server: { port: 5176, host: '127.0.0.1', strictPort: true,
  proxy: { '/api': { target: 'http://127.0.0.1:8008', changeOrigin: true } } } }))
