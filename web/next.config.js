/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // 把 /api/* 代理到 FastAPI（避免浏览器 CORS）
    // 默认指向 18002，可以通过环境变量覆盖
    const apiTarget = process.env.API_PROXY_TARGET || "http://localhost:18002";
    return [
      { source: "/api/:path*", destination: `${apiTarget}/api/:path*` },
      { source: "/charts/:path*", destination: `${apiTarget}/api/v1/charts/:path*` },
    ];
  },
};

module.exports = nextConfig;