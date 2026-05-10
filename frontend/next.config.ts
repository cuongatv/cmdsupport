import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  output: 'standalone',
  // CI already runs `tsc --noEmit` in a dedicated job that gates the deploy,
  // so re-running it inside `next build` is duplicate work that frequently
  // OOMs / hangs on small production servers and blows past the SSH command
  // timeout. Lint quality is enforced upstream in CI. (Next.js 16 no longer
  // runs ESLint during build, so no `eslint` field is needed here.)
  typescript: { ignoreBuildErrors: true },
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
