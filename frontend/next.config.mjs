import path from "node:path";
import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
const backend = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig = {
  // standalone-сборка нужна только образу Docker (NEXT_OUTPUT=standalone в Dockerfile); локальный запуск — next start
  ...(process.env.NEXT_OUTPUT === "standalone" ? { output: "standalone" } : {}),
  // корень проекта — эта папка, даже если выше по дереву лежит чужой package-lock.json
  outputFileTracingRoot: path.dirname(fileURLToPath(import.meta.url)),
  reactStrictMode: true,
  // разбор потребности локальной LLM ждёт до 45 с (LLM_INTERACTIVE_TIMEOUT_S); по умолчанию прокси Next рвёт через 30 с
  experimental: { proxyTimeout: 60_000 },
  // Фронтенд проксирует /api на бэкенд: cookie сессии остаётся first-party, CORS не нужен
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
