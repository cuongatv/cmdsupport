"use client";

import React from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { WikiGraphData, WikiPageDetail } from "@/types/wiki";
import { WikiGraphMini } from "./wiki-graph";
import { WikiTaxonomyBadge, WikiTypeBadge } from "./wiki-type-badge";
import { ScopeBadge } from "@/components/shared/scope-badge";

type Props = {
  slug: string;
  page: WikiPageDetail;
};

function LinkItem({
  slug,
  direction,
}: {
  slug: string;
  direction: "back" | "forward";
}) {
  const label = slug.split("/").pop() ?? slug;
  return (
    <Link
      href={`/admin/wiki/${slug}`}
      className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs text-muted-foreground hover:bg-accent/50 hover:text-foreground transition-colors group"
    >
      <span className="material-symbols-outlined text-xs text-muted-foreground group-hover:text-primary transition-colors">
        {direction === "back" ? "arrow_back" : "arrow_forward"}
      </span>
      <span className="truncate" title={slug}>
        {label}
      </span>
    </Link>
  );
}

function Section({
  title,
  icon,
  count,
  defaultOpen = true,
  children,
}: {
  title: string;
  icon: string;
  count: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  if (count === 0) return null;
  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors"
      >
        <span className="material-symbols-outlined text-xs">{icon}</span>
        {title}
        <span className="ml-auto tabular-nums">{count}</span>
        <span className="material-symbols-outlined text-xs">
          {open ? "expand_less" : "expand_more"}
        </span>
      </button>
      {open && <div className="space-y-0.5">{children}</div>}
    </div>
  );
}

export function WikiSidebarRight({ slug, page }: Props) {
  const [graphData, setGraphData] = React.useState<WikiGraphData | null>(null);

  React.useEffect(() => {
    api<WikiGraphData>(`/api/wiki/graph?slug=${encodeURIComponent(slug)}&depth=1`)
      .then((d) => setGraphData(d))
      .catch(() => setGraphData(null));
  }, [slug]);

  return (
    <div className="w-72 shrink-0 border-l border-border bg-card/30 flex flex-col overflow-hidden h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <span className="material-symbols-outlined text-sm text-muted-foreground">
          info
        </span>
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Thông tin trang
        </span>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {/* Metadata section */}
        <div className="space-y-3">
          {/* Type + Scope */}
          <div className="flex flex-wrap items-center gap-1.5">
            <WikiTypeBadge type={page.page_type} />
            <ScopeBadge scopeType={page.scope_type ?? "global"} scopeId={page.scope_id} />
          </div>

          {/* Version & Date */}
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <p className="text-muted-foreground/60 mb-0.5">Phiên bản</p>
              <p className="text-foreground font-medium">v{page.version}</p>
            </div>
            <div>
              <p className="text-muted-foreground/60 mb-0.5">Ngày cập nhật</p>
              <p className="text-foreground font-medium">
                {new Date(page.updated_at).toLocaleDateString("vi-VN", {
                  day: "2-digit",
                  month: "2-digit",
                  year: "numeric",
                })}
              </p>
            </div>
          </div>

          {/* Knowledge Types */}
          {page.knowledge_type_slugs.length > 0 && (
            <div>
              <p className="text-xs text-muted-foreground/60 mb-1.5">Loại tri thức</p>
              <div className="flex flex-wrap gap-1">
                {page.knowledge_type_slugs.map((kt) => (
                  <WikiTaxonomyBadge key={kt} slug={kt} />
                ))}
              </div>
            </div>
          )}

          {/* Source documents */}
          {page.source_ids.length > 0 && (
            <div>
              <p className="text-xs text-muted-foreground/60 mb-1.5">
                Tài liệu nguồn ({page.source_ids.length})
              </p>
              <Link
                href="/admin/knowledge"
                className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs text-muted-foreground hover:bg-accent/50 hover:text-foreground transition-colors"
              >
                <span className="material-symbols-outlined text-xs">open_in_new</span>
                Xem trong Kho tri thức
              </Link>
            </div>
          )}
        </div>

        <hr className="border-border" />

        {/* Connections */}
        {(page.backlinks.length > 0 || page.outlinks.length > 0) ? (
          <>
            <Section title="Liên kết đến" icon="arrow_back" count={page.backlinks.length}>
              {page.backlinks.map((s) => (
                <LinkItem key={s} slug={s} direction="back" />
              ))}
            </Section>
            <Section title="Liên kết đi" icon="arrow_forward" count={page.outlinks.length}>
              {page.outlinks.map((s) => (
                <LinkItem key={s} slug={s} direction="forward" />
              ))}
            </Section>
          </>
        ) : (
          <p className="text-xs text-muted-foreground py-1">Chưa có liên kết nào.</p>
        )}
      </div>

      {/* Mini graph pinned to bottom */}
      {graphData && graphData.nodes.length > 0 && (
        <div className="shrink-0 border-t border-border p-4 bg-card/40">
          <div className="flex items-center gap-2 pb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <span className="material-symbols-outlined text-xs">hub</span>
            Đồ thị cục bộ
          </div>
          <div className="rounded-xl overflow-hidden border border-border shadow-sm">
            <WikiGraphMini
              slug={slug}
              nodes={graphData.nodes}
              edges={graphData.edges}
            />
          </div>
        </div>
      )}
    </div>
  );
}

// Keep backward-compatible export name
export { WikiSidebarRight as WikiBacklinks };
