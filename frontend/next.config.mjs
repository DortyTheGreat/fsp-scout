/** @type {import('next').NextConfig} */
const backend = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  // разбор потребности локальной LLM ждёт до 45 с (LLM_INTERACTIVE_TIMEOUT_S); по умолчанию прокси Next рвёт через 30 с
  experimental: { proxyTimeout: 60_000 },
  // Фронтенд проксирует /api на бэкенд: cookie сессии остаётся first-party, CORS не нужен
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
