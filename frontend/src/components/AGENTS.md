# frontend/src/components/ — React components

## OVERVIEW
Two flavors of folder: **shadcn primitives** in `ui/` (don't restyle), and **feature folders** named after the route they back. Shared cross-feature pieces live in `shared/` and `layout/`.

## STRUCTURE
```
components/
├── ui/                  # shadcn/ui v4 primitives — DO NOT restyle, override at usage site
├── layout/              # sidebar.tsx, header, app shell
├── shared/              # cross-feature reusables (modals, empty states, ...)
├── audit/               # /admin/audit page
├── cmd-support/         # /admin/cmd-advisory + /cmd-advisory pages (folder name kept legacy; component lib reused)
├── dashboard/           # /admin (root) page widgets
├── departments/         # /admin/departments
├── employees/           # /admin/employees
├── knowledge/           # /admin/knowledge
│   └── knowledge-table/ # nested when a feature outgrows one file
├── profile/             # /admin/profile
├── projects/            # /admin/projects + /admin/tasks/projects/[id]
│   └── project-detail/  # nested
├── roles/               # /admin/roles
├── settings/            # /admin/settings
├── skills/              # /admin/skills
├── tasks/               # /admin/tasks (largest feature folder, 13 files)
├── types/               # /admin/types — knowledge type management
└── wiki/                # /admin/wiki
    └── wiki-graph/      # d3-force visualization
```

## CONVENTIONS
- **Folder name = route segment.** New page at `/admin/foo` → new folder `components/foo/`.
- **Filenames are kebab-case**, exports are PascalCase. `task-dashboard.tsx` exports `TaskDashboard`.
- **A feature outgrowing one file** (>~6 components or >~500 lines) gets a sub-folder named after the dominant component (`knowledge-table/`, `project-detail/`, `wiki-graph/`).
- **Index files**: only when there's a public surface to flatten (e.g. `knowledge-table/index.tsx`). Don't add `index.ts` everywhere just to shorten imports.
- **Server vs client**: leaf components are usually `"use client"`. Lift fetch into the page (RSC) when possible.

## CONVENTIONS — `ui/` ONLY
- These are shadcn-generated. **Don't edit them to change visual design** — override via `className` at the call site, or change Tailwind tokens in `globals.css`.
- If you need a new primitive, prefer `npx shadcn@latest add <name>` so future shadcn updates can replay cleanly.

## ANTI-PATTERNS
- **Don't put feature logic in `ui/`.** It's the primitive layer; mixing in feature code makes shadcn updates painful.
- **Don't reach across feature folders.** If `tasks/` needs something from `projects/`, lift the shared piece into `shared/`.
- **Don't co-locate `*.test.tsx`** — Playwright e2e lives in `frontend/tests/`, and there is no unit-test runner installed.
- **Don't create a generic `<Modal>`/`<Button>`** when `ui/dialog.tsx` / `ui/button.tsx` already exist. Compose, don't duplicate.
