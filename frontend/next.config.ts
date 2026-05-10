import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  output: 'standalone',
  async redirects() {
    return [
      { source: '/cmd-support', destination: '/', permanent: false },
      { source: '/cmd-support/history', destination: '/admin/cmd-support/history', permanent: false },
      { source: '/cmd-support/:id', destination: '/admin/cmd-support/:id', permanent: false },
    ];
  },
  async rewrites() {
    const apiBase = process.env.INTERNAL_API_URL ?? 'http://127.0.0.1:5055';
    return [
      {
        source: '/api/:path*',
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
