import { WikiPageType } from "@/types/wiki";
import { getWikiPageTypeLabel } from "@/lib/wiki-labels";

const TYPE_CONFIG: Record<
  WikiPageType,
  { icon: string; label: string; color: string; bg: string }
> = {
  entity: {
    icon: "person",
    label: getWikiPageTypeLabel("entity"),
    color: "#006B68",
    bg: "rgba(0,107,104,0.1)",
  },
  concept: {
    icon: "lightbulb",
    label: getWikiPageTypeLabel("concept"),
    color: "#8c7b6b",
    bg: "rgba(140,123,107,0.1)",
  },
  topic: {
    icon: "topic",
    label: getWikiPageTypeLabel("topic"),
    color: "#6b8c7b",
    bg: "rgba(107,140,123,0.1)",
  },
  source: {
    icon: "description",
    label: getWikiPageTypeLabel("source"),
    color: "#7b6b8c",
    bg: "rgba(123,107,140,0.1)",
  },
  index: {
    icon: "list_alt",
    label: getWikiPageTypeLabel("index"),
    color: "#5F7676",
    bg: "rgba(95,118,118,0.1)",
  },
  log: {
    icon: "history",
    label: getWikiPageTypeLabel("log"),
    color: "#5F7676",
    bg: "rgba(95,118,118,0.1)",
  },
};

export function WikiTypeBadge({ type }: { type: string }) {
  const cfg = TYPE_CONFIG[type as WikiPageType] ?? TYPE_CONFIG.concept;
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium"
      style={{ color: cfg.color, backgroundColor: cfg.bg, border: `1px solid ${cfg.color}40` }}
    >
      <span className="material-symbols-outlined" style={{ fontSize: 12 }}>
        {cfg.icon}
      </span>
      {cfg.label}
    </span>
  );
}

export function wikiTypeIcon(type: string): string {
  return TYPE_CONFIG[type as WikiPageType]?.icon ?? "article";
}

export function wikiTypeColor(type: string): string {
  return TYPE_CONFIG[type as WikiPageType]?.color ?? "#5F7676";
}

export function wikiTypeGroupLabel(type: string): string {
  switch (type) {
    case "entity":
    case "concept":
    case "topic":
    case "source":
    case "index":
    case "log":
      return getWikiPageTypeLabel(type as WikiPageType);
    default:
      return type;
  }
}
