<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

Next.js **16.2.4** + React **19.2.4** + Tailwind **4** + the React Compiler are all on the bleeding edge. APIs, conventions, and file structure differ from any model's training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

## STACK
- **Next.js 16.2.4** — App Router, `output: "standalone"`, `reactCompiler: true`
- **React 19.2.4** + `babel-plugin-react-compiler@1.0.0`
- **Tailwind 4** via `@tailwindcss/postcss` (no `tailwind.config.js` — config is in CSS)
- **shadcn/ui v4** (components in `src/components/ui/`)
- **Base UI** (`@base-ui/react`) for primitives
- **dnd-kit** for drag/drop, **d3-force/drag** for the wiki graph
- **lucide-react** icons (Material Symbols Outlined for sidebar — see `DESIGN.md`)
- **Playwright** for e2e (no Jest/Vitest — see `tests/AGENTS.md` style: `frontend/tests/*.spec.ts`)

## STRUCTURE
```
frontend/
├── src/
│   ├── app/         # App Router routes (route groups (public)/(portal)) — see src/app/AGENTS.md
│   ├── components/  # Feature folders + shadcn ui/ — see src/components/AGENTS.md
│   ├── lib/         # api.ts, auth.tsx, utils, design tokens
│   └── types/       # Shared TS types
├── public/          # Static assets, favicons
├── tests/           # Playwright e2e (.spec.ts)
├── next.config.ts   # rewrites /api/* → INTERNAL_API_URL (api:5055 in prod / 127.0.0.1:5055 in dev)
├── playwright.config.ts  # Chromium-only, no webServer (assumes Docker stack on :3119)
└── eslint.config.mjs # See CONVENTIONS below
```

## CONVENTIONS
- **HTTP**: `import { api } from "@/lib/api"`. **Never** call `fetch` directly. `api()` handles auth header + base URL + 401 redirect.
- **Auth state**: `import { useAuth } from "@/lib/auth"`. The provider is mounted in `src/app/layout.tsx`.
- **Design tokens**: BIDV teal `#2D8380` and the rest live in `DESIGN.md` + `src/app/globals.css`. Use Tailwind tokens, not raw hex.
- **Path alias**: `@/*` → `./src/*` (set in `tsconfig.json`).
- **File naming**: components `PascalCase.tsx`, everything else kebab-case. (Files use kebab; `export` is PascalCase.)
- **ESLint** (`eslint.config.mjs`) downgrades 3 React 19 hook rules to `warn` so legacy patterns don't break CI:
  `react-hooks/set-state-in-effect`, `react-hooks/refs`, `react-hooks/preserve-manual-memoization`.
  Don't silence them further — fix them when you touch the file.

## COMMANDS
```bash
npm install            # uses package-lock.json
npm run dev            # http://localhost:3000  (or :3119 via docker)
npm run build          # next build (skips tsc; ignoreBuildErrors: true)
npm run lint           # eslint
npx tsc --noEmit       # CI runs this; next build does NOT
npm run test:e2e       # Playwright; requires Docker stack on :3119
```

## ANTI-PATTERNS
- **Don't add `as any`, `@ts-ignore`, `@ts-expect-error`** to make `tsc` shut up. CI runs `tsc --noEmit` separately and will fail the deploy. Fix the type instead.
- **Don't `fetch` directly.** Always `api()` from `@/lib/api`.
- **Don't add a `tailwind.config.js`** — Tailwind 4 reads config from CSS (`globals.css`). Adding the JS config silently disables it.
- **Don't bypass `next.config.ts` rewrites** with absolute API URLs in dev. Same-origin avoids the Chromium "Private Network Access" prompt.
- **Don't run `next build` to typecheck.** It's deliberately turned off (`typescript.ignoreBuildErrors: true`) because building on a small server with the typecheck on OOMs / hangs.
- **Don't read `node_modules/next/dist/docs/`** for general questions — only when you need the exact Next 16 contract. For project rules, this file is enough.
