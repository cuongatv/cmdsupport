/**
 * Frontend feature flags for the Agile upgrade rollout.
 *
 * Mirror of the backend `FEATURE_AGILE_PHASE_*` flags in `app/config.py`.
 * Default OFF for every phase — opt-in via Next.js public env vars so the
 * value is inlined at build time and is safe to read from client components.
 *
 *   NEXT_PUBLIC_FEATURE_AGILE_PHASE_1=true   # Kanban WIP + aging UI
 *   NEXT_PUBLIC_FEATURE_AGILE_PHASE_2=true   # Sprint + task semantics UI
 *   NEXT_PUBLIC_FEATURE_AGILE_PHASE_3=true   # Squad capacity overview UI
 *   NEXT_PUBLIC_FEATURE_AGILE_PHASE_4=true   # Task knowledge links + DoR/DoD templates UI
 *   NEXT_PUBLIC_FEATURE_AGILE_PHASE_5=true   # Vietnamese flow metrics + governance advisory UI
 *
 * Anything outside `"true"` (including unset, `false`, `"1"`, ...) keeps the
 * UI in its pre-Phase-N shape so legacy deployments stay untouched.
 */

function readBoolFlag(value: string | undefined): boolean {
  return typeof value === "string" && value.toLowerCase() === "true";
}

export const FEATURE_AGILE_PHASE_1: boolean = readBoolFlag(
  process.env.NEXT_PUBLIC_FEATURE_AGILE_PHASE_1,
);

export const FEATURE_AGILE_PHASE_2: boolean = readBoolFlag(
  process.env.NEXT_PUBLIC_FEATURE_AGILE_PHASE_2,
);

export const FEATURE_AGILE_PHASE_3: boolean = readBoolFlag(
  process.env.NEXT_PUBLIC_FEATURE_AGILE_PHASE_3,
);

export const FEATURE_AGILE_PHASE_4: boolean = readBoolFlag(
  process.env.NEXT_PUBLIC_FEATURE_AGILE_PHASE_4,
);

export const FEATURE_AGILE_PHASE_5: boolean = readBoolFlag(
  process.env.NEXT_PUBLIC_FEATURE_AGILE_PHASE_5,
);
