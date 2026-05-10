"use client";

import React from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { WikiPageSummary } from "@/types/wiki";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { WikiPageTree } from "@/components/wiki/wiki-page-tree";
import { WikiContent } from "@/components/wiki/wiki-content";
import { WikiTypeBadge, wikiTypeGroupLabel } from "@/components/wiki/wiki-type-badge";
import { ScopeBadge } from "@/components/shared/scope-badge";
import { WikiSearchDialog } from "@/components/wiki/wiki-search-dialog";
import { EmptyState } from "@/components/shared/empty-state";

const TYPE_TABS = ["all", "entity", "concept", "topic", "source"] as const;

export default function WikiIndexPage() {
  const [indexMd, setIndexMd] = React.useState<string | null>(null);
  const [allPages, setAllPages] = React.useState<WikiPageSummary[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [searchOpen, setSearchOpen] = React.useState(false);
  const [activeTab, setActiveTab] = React.useState<string>("all");

  React.useEffect(() => {
    Promise.all([
      api<{ content_md: string }>("/api/wiki/index"),
      api<WikiPageSummary[]>("/api/wiki/pages?limit=200"),
    ])
      .then(([idx, pages]) => {
        setIndexMd(idx.content_md || null);
        const filtered = Array.isArray(pages)
          ? pages.filter((p) => p.page_type !== "index" && p.page_type !== "log")
          : [];
        setAllPages(filtered);
      })
      .catch(() => {})
      .finally(() => setLoading(false));

    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Stats
  const totalPages = allPages.length;
  const typeCounts = React.useMemo(() => {
    const c: Record<string, number> = {};
    for (const p of allPages) c[p.page_type] = (c[p.page_type] ?? 0) + 1;
    return c;
  }, [allPages]);
  const lastUpdated = allPages[0]?.updated_at;

  // Filter by tab
  const displayPages = React.useMemo(() => {
    const list = activeTab === "all"
      ? allPages
      : allPages.filter((p) => p.page_type === activeTab);
    return list.slice(0, 24);
  }, [allPages, activeTab]);

  return (
    <>
      <PageHeader
        title="Tri thức Wiki"
        description="Tri thức được tổng hợp từ tài liệu của tổ chức."
        action={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={() => setSearchOpen(true)}
              className="gap-2"
            >
              <span className="material-symbols-outlined text-base">search</span>
              Tìm kiếm
              <kbd className="hidden sm:inline-block ml-1 px-1.5 py-0.5 rounded border border-border text-xs font-mono text-muted-foreground">
                ⌘K
              </kbd>
            </Button>
            <Link
               href="/admin/wiki/graph"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              <span className="material-symbols-outlined text-base">hub</span>
              Đồ thị
            </Link>
          </div>
        }
      />

      <div className="flex-1 flex gap-0 -mx-6 md:-mx-8 lg:-mx-10 -mb-6 md:-mb-8 lg:-mb-10 min-h-0 border-t border-border">
        {/* Page Tree */}
        <WikiPageTree />

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-8 py-6">
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
                progress_activity
              </span>
            </div>
          ) : indexMd ? (
            <>
              {/* Stats bar */}
              {totalPages > 0 && (
                <div className="flex flex-wrap items-center gap-3 mb-8">
                  <div className="flex items-center gap-2 bg-card border border-border rounded-xl px-4 py-2.5 shadow-sahara">
                    <span className="material-symbols-outlined text-base text-primary">article</span>
                    <span className="text-sm font-semibold text-foreground">{totalPages}</span>
                    <span className="text-xs text-muted-foreground">Trang</span>
                  </div>
                  {Object.entries(typeCounts).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
                    <div
                      key={type}
                      className="flex items-center gap-1.5 bg-card border border-border rounded-xl px-3 py-2.5 shadow-sahara"
                    >
                      <WikiTypeBadge type={type} />
                      <span className="text-xs text-muted-foreground tabular-nums">{count}</span>
                    </div>
                  ))}
                  {lastUpdated && (
                    <div className="flex items-center gap-2 bg-card border border-border rounded-xl px-4 py-2.5 shadow-sahara ml-auto">
                      <span className="material-symbols-outlined text-base text-muted-foreground">schedule</span>
                      <span className="text-xs text-muted-foreground">
                        Cập nhật {new Date(lastUpdated).toLocaleDateString("vi-VN", {
                          day: "numeric",
                          month: "short",
                        })}
                      </span>
                    </div>
                  )}
                </div>
              )}

              <WikiContent markdown={indexMd} />

              {/* Pages grid */}
              {allPages.length > 0 && (
                <div className="mt-12">
                  {/* Type tabs */}
                  <div className="flex items-center gap-1 mb-5 border-b border-border">
                    {TYPE_TABS.map((tab) => {
                      const count = tab === "all"
                        ? totalPages
                        : typeCounts[tab] ?? 0;
                      if (tab !== "all" && count === 0) return null;
                      return (
                        <button
                          key={tab}
                          onClick={() => setActiveTab(tab)}
                          className={`px-3 py-2 text-xs font-medium capitalize border-b-2 transition-colors ${
                            activeTab === tab
                              ? "border-primary text-primary"
                              : "border-transparent text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          {tab === "all" ? "Tất cả" : wikiTypeGroupLabel(tab)}
                          <span className="ml-1.5 tabular-nums text-muted-foreground">
                            {count}
                          </span>
                        </button>
                      );
                    })}
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                    {displayPages.map((page) => (
                      <Link
                        key={page.slug}
                        href={`/wiki/${page.slug}`}
                        className="group block bg-card border border-border rounded-xl p-4 hover:border-primary/40 hover:shadow-sahara transition-all"
                      >
                        <div className="flex items-start justify-between gap-2 mb-2">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <WikiTypeBadge type={page.page_type} />
                            {page.scope_type && page.scope_type !== "global" && (
                              <ScopeBadge scopeType={page.scope_type} scopeId={page.scope_id} />
                            )}
                          </div>
                          <span className="text-xs text-muted-foreground shrink-0">
                            v{page.version}
                          </span>
                        </div>
                        <h3 className="font-heading text-base font-normal text-foreground group-hover:text-primary transition-colors mb-1">
                          {page.title}
                        </h3>
                        {page.summary && (
                          <p className="text-xs text-muted-foreground line-clamp-2">
                            {page.summary}
                          </p>
                        )}
                        <p className="text-xs text-muted-foreground mt-3">
                          {new Date(page.updated_at).toLocaleDateString()}
                        </p>
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <EmptyState
              icon="auto_stories"
              title="Wiki chưa có nội dung"
              description="Tải lên và biên dịch tài liệu để bắt đầu xây dựng tri thức wiki."
            />
          )}
        </div>
      </div>

      <WikiSearchDialog open={searchOpen} onOpenChange={setSearchOpen} />
    </>
  );
}
