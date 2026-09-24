import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

/**
 * Vite 配置
 * - 开发期用 proxy 把 /api 转到 Flask（5000），浏览器只访问同源地址，彻底绕开跨域；
 *   后端 CORS 虽然已放开，但代理方案在论文部署说明里更好讲，也便于以后加鉴权。
 * - 生产构建后的产物交给 nginx / Flask 静态目录，接口地址改走 .env.production 的绝对 URL。
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [vue()],
    resolve: {
      // @ 指向 src，避免 ../../../ 这类相对路径在改版时集体失效
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      host: '0.0.0.0',
      port: Number(env.VITE_DEV_PORT || 5173),
      // 本地默认自动开浏览器；脚本化联调（CI/验证）时把 VITE_DEV_OPEN 设为 0 关掉
      open: env.VITE_DEV_OPEN !== '0',
      proxy: {
        '/api': {
          target: env.VITE_PROXY_TARGET || 'http://127.0.0.1:5000',
          changeOrigin: true,
          // 后端路由本身就带 /api 前缀，所以这里不做 rewrite
          ws: false,
          configure: (proxy) => {
            // 后端没起时给一条明确日志，比前端一片空白好定位
            proxy.on('error', (e) => console.error('[proxy] 后端不可访问：', e.message))
          },
        },
      },
    },
    build: {
      outDir: 'dist',
      chunkSizeWarningLimit: 1600,
      rollupOptions: {
        // echarts 和 element-plus 体积大且不常改，单独切包利于浏览器缓存
        output: { manualChunks: { echarts: ['echarts'], 'element-plus': ['element-plus'] } },
      },
    },
  }
})
