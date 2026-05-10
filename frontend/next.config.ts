import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  output: 'standalone',
  // CI already runs `tsc --noEmit` and `eslint` in dedicated jobs that gate
  // the deploy. Re-running them inside `next build` (a) duplicates work and
  // (b) frequently OOMs / hangs on small production servers, blowing past the
  // SSH-action command timeout. Skip them here; lint quality is enforced
  // upstream in CI.
  typescript: { ignoreBuildErrors: true },
  eslint: { ignoreDuringBuilds: true },
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
