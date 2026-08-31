import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 开发端口固定为 5173：后端 app/main.py 的 _frontend_url() 指向它
export default defineConfig({
  plugins: [vue()],
  base: "./",
  server: { port: 5173, strictPort: true },
  build: { outDir: "dist", assetsDir: "assets" },
});
