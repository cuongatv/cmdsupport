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
  // Next.js rewrites() upstream proxy defaults to 30s timeout (see
  // node_modules/next/dist/server/lib/router-utils/proxy-request.js line 33).
  // The CMD advisory LLM call regularly takes 45-90s (and up to 5 min when
  // gateway 504 retries trigger the 15+45+120s backoff in
  // app/ai/providers/openai_provider.py:_create_chat). At the default 30s,
  // the proxy ECONNRESETs and the browser sees "API Error 500" even though
  // the backend succeeds. Bump to 5 minutes to match the frontend api()
  // timeoutMs in src/lib/api.ts.
  //
  // Next.js 16 also caps proxied request bodies at 10MB by default
  // (`experimental.proxyClientMaxBodySize`). Knowledge Base uploads allow up
  // to 50MB (see MAX_UPLOAD_BYTES in src/lib/api.ts and nginx
  // client_max_body_size), so the proxy limit must match — otherwise large
  // files are silently truncated and the browser sees a frontend abort
  // ("Tải lên quá thời gian chờ") instead of reaching the FastAPI backend.
  experimental: {
    proxyTimeout: 300_000,
    proxyClientMaxBodySize: 50 * 1024 * 1024,
  },
  async redirects() {
    return [
      // Legacy public/admin "cmd-support" URLs → new "cmd-advisory" routes.
      // Public advisory form moved from `/` to `/cmd-advisory`; root `/` is now
      // an auth-aware redirect handled in (public)/page.tsx.
      { source: '/cmd-support', destination: '/cmd-advisory', permanent: false },
      { source: '/cmd-support/history', destination: '/admin/cmd-advisory/history', permanent: false },
      { source: '/cmd-support/rules', destination: '/admin/cmd-advisory/rules', permanent: false },
      { source: '/cmd-support/:id', destination: '/admin/cmd-advisory/:id', permanent: false },
      { source: '/admin/cmd-support', destination: '/admin/cmd-advisory', permanent: false },
      { source: '/admin/cmd-support/history', destination: '/admin/cmd-advisory/history', permanent: false },
      { source: '/admin/cmd-support/rules', destination: '/admin/cmd-advisory/rules', permanent: false },
      { source: '/admin/cmd-support/:id', destination: '/admin/cmd-advisory/:id', permanent: false },
    ];
  },
  async rewrites() {
    // `rewrites()` is evaluated at BUILD TIME for the standalone output, so
    // INTERNAL_API_URL must be readable when `next build` runs. Inside the
    // Dockerfile builder stage that env var is NOT set, so we fall back based
    // on NODE_ENV (which Next forces to 'production' during `next build`):
    //   - production build (docker)  -> http://api:5055   (compose service DNS)
    //   - dev build / `next dev`     -> http://127.0.0.1:5055 (local API)
    // Override explicitly with INTERNAL_API_URL when needed.
    const apiBase =
      process.env.INTERNAL_API_URL ??
      (process.env.NODE_ENV === 'production'
        ? 'http://api:5055'
        : 'http://127.0.0.1:5055');
    return [
      {
        source: '/api/:path*',
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
