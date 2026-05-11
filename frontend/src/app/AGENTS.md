# frontend/src/app/ — App Router routes

## OVERVIEW
Next.js 16 App Router with two route groups: `(public)` (unauthenticated marketing/landing) and `(portal)` (authenticated admin SPA). Login lives at the top level under `/login`. Auth gating happens in `(portal)/admin/layout.tsx`, NOT in middleware.

## STRUCTURE
```
src/app/
├── layout.tsx                       # Root shell: <html>, font, AuthProvider
├── login/page.tsx                   # /login — outside both route groups
├── (public)/
│   ├── layout.tsx                   # Public shell (no sidebar)
│   └── page.tsx                     # /  (landing)
└── (portal)/admin/
    ├── layout.tsx                   # Portal shell + auth redirect to /login
    ├── page.tsx                     # /admin (dashboard)
    ├── audit/page.tsx               # /admin/audit
    ├── cmd-support/
    │   ├── page.tsx                 # /admin/cmd-support
    │   ├── history/page.tsx
    │   └── [id]/page.tsx
    ├── departments/page.tsx
    ├── employees/page.tsx
    ├── knowledge/page.tsx
    ├── profile/page.tsx
    ├── projects/page.tsx
    ├── roles/page.tsx
    ├── settings/page.tsx
    ├── skills/
    │   ├── page.tsx                 # /admin/skills
    │   └── [slug]/page.tsx, edit/page.tsx
    ├── tasks/
    │   ├── page.tsx                 # /admin/tasks
    │   └── projects/[id]/page.tsx
    ├── wiki/
    │   ├── page.tsx                 # /admin/wiki
    │   ├── graph/page.tsx           # full-screen knowledge graph
    │   └── [...slug]/page.tsx       # catch-all for nested wiki paths
    └── workspaces/
        ├── page.tsx
        └── [id]/page.tsx
```

## ROUTING CONVENTIONS
- **Route groups `()`** are URL-invisible — `(portal)/admin/page.tsx` serves `/admin`, NOT `/portal/admin`.
- **Catch-all `[...slug]`** is used only for wiki nested paths. New deep-tree routes should follow that pattern.
- **`next.config.ts` redirects** quietly forward `/cmd-support*` → `/admin/cmd-support*`. Don't link to `/cmd-support` directly in new code; use the canonical `/admin/cmd-support` URL.
- **Auth gate in `(portal)/admin/layout.tsx`**: it reads `useAuth()` and pushes to `/login` if no session. There is no Next.js `middleware.ts`.

## ANTI-PATTERNS
- **Don't add a `middleware.ts`** for auth — the layout-level guard is intentional and works with the React Compiler. Adding middleware doubles the redirect logic.
- **Don't put a page directly in `(public)/admin/...` or `(portal)/page.tsx`** — keep the public/portal split clean.
- **Don't add a top-level `page.tsx` outside a route group** — `(public)/page.tsx` IS the home page.
- **Don't add `"use client"` to a route layout** unless you genuinely need it. The portal layout is a client component (auth state); most others should stay server.
