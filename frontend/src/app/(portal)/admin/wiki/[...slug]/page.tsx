"use client";

import React from "react";
import { useParams, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { WikiPageDetail, DraftResponse } from "@/types/wiki";
import { WikiPageTree } from "@/components/wiki/wiki-page-tree";
import { WikiContent } from "@/components/wiki/wiki-content";
import { WikiSidebarRight } from "@/components/wiki/wiki-backlinks";
import { WikiEditor } from "@/components/wiki/wiki-editor";
import { WikiDraftBanner } from "@/components/wiki/wiki-draft-banner";
import { wikiTypeGroupLabel } from "@/components/wiki/wiki-type-badge";
import { WikiSearchDialog } from "@/components/wiki/wiki-search-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import Link from "next/link";

const WORKSPACE_ROLE_LEVEL: Record<string, number> = {
  viewer: 0,
  contributor: 1,
  editor: 2,
  admin: 3,
};

function roleAtLeast(role: string | null, min: string): boolean {
  if (!role) return false;
  return (WORKSPACE_ROLE_LEVEL[role] ?? -1) >= (WORKSPACE_ROLE_LEVEL[min] ?? 999);
}

export default function WikiPageViewer() {
  const params = useParams();
  const searchParams = useSearchParams();
  const { user, getWorkspaceRole, hasPermission } = useAuth();

  const slugParts = Array.isArray(params.slug) ? params.slug : [params.slug ?? ""];
  const fullSlug = slugParts.join("/");
  const scopeType = searchParams.get("scopeType") || undefined;
  const scopeId = searchParams.get("scopeId") || undefined;
  const isScoped = !!scopeType && scopeType !== "global";

  const [page, setPage] = React.useState<WikiPageDetail | null>(null);
  const [notFound, setNotFound] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [searchOpen, setSearchOpen] = React.useState(false);

  // Edit mode
  const [mode, setMode] = React.useState<"view" | "edit">("view");

  // Pending drafts (for editors/admins)
  const [drafts, setDrafts] = React.useState<DraftResponse[]>([]);

  // ---------------------------------------------------------------------------
  // Permission helpers
  // ---------------------------------------------------------------------------
  const wsRole = isScoped && scopeId ? getWorkspaceRole(scopeId) : null;
  const isGlobalAdmin = user?.role === "admin";

  // Can directly edit (PUT /wiki/pages/{slug})
  const canEdit: boolean = (() => {
    if (!user) return false;
    if (isGlobalAdmin) return true;
    if (isScoped) return roleAtLeast(wsRole, "editor");
    return hasPermission("wiki:write:all");
  })();

  // Can propose draft (POST /wiki/pages/{slug}/drafts)
  const canPropose: boolean = (() => {
    if (!user) return false;
    if (canEdit) return true; // editors can also propose
    if (isScoped) return roleAtLeast(wsRole, "contributor");
    return hasPermission("wiki:write:own_dept") || hasPermission("wiki:write:all");
  })();

  // Can review drafts
  const canReview: boolean = canEdit;

  // ---------------------------------------------------------------------------
  // Load page
  // ---------------------------------------------------------------------------
  React.useEffect(() => {
    if (!fullSlug) return;
    setLoading(true);
    setNotFound(false);
    setPage(null);
    setMode("view");

    const scopeParams = isScoped ? `?scope_type=${scopeType}&scope_id=${scopeId}` : "";
    api<WikiPageDetail>(`/api/wiki/pages/${encodeURIComponent(fullSlug)}${scopeParams}`)
      .then((data) => setPage(data))
      .catch((err) => {
        if (err?.status === 404 || err?.message?.includes("404")) {
          setNotFound(true);
        }
      })
      .finally(() => setLoading(false));
  }, [fullSlug, scopeType, scopeId, isScoped]);

  // ---------------------------------------------------------------------------
  // Load pending drafts (editors/admins only, after page loaded)
  // ---------------------------------------------------------------------------
  const fetchDrafts = React.useCallback(() => {
    if (!page || !canReview) return;
    api<DraftResponse[]>(
      `/api/wiki/pages/${encodeURIComponent(fullSlug)}/drafts${isScoped ? `?scope_type=${scopeType}&scope_id=${scopeId}` : ""}`
    )
      .then((data) => setDrafts(data.filter((d) => d.status === "pending")))
      .catch(() => setDrafts([]));
  }, [page, canReview, fullSlug, isScoped, scopeType, scopeId]);

  React.useEffect(() => {
    fetchDrafts();
  }, [fetchDrafts]);

  // ---------------------------------------------------------------------------
  // Keyboard shortcut: ⌘K search
  // ---------------------------------------------------------------------------
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // ---------------------------------------------------------------------------
  // Save handlers
  // ---------------------------------------------------------------------------
  const handleSaveEdit = async (content: string, note: string) => {
    const scopeParams = isScoped ? `?scope_type=${scopeType}&scope_id=${scopeId}` : "";
    const updated = await api<WikiPageDetail>(
      `/api/wiki/pages/${encodeURIComponent(fullSlug)}${scopeParams}`,
      {
        method: "PUT",
        body: { content_md: content, change_note: note || undefined },
      }
    );
    setPage(updated);
    setMode("view");
  };

  const handleSaveProposal = async (content: string, note: string) => {
    const scopeParams = isScoped ? `?scope_type=${scopeType}&scope_id=${scopeId}` : "";
    await api(
      `/api/wiki/pages/${encodeURIComponent(fullSlug)}/drafts${scopeParams}`,
      {
        method: "POST",
        body: { content_md: content, note: note || undefined },
      }
    );
    setMode("view");
  };

  const handleDraftApproved = (draftId: string) => {
    setDrafts((prev) => prev.filter((d) => d.id !== draftId));
    // Reload page content — the approved draft has been applied
    const scopeParams = isScoped ? `?scope_type=${scopeType}&scope_id=${scopeId}` : "";
    api<WikiPageDetail>(`/api/wiki/pages/${encodeURIComponent(fullSlug)}${scopeParams}`)
      .then(setPage)
      .catch(() => {});
  };

  const handleDraftRejected = (draftId: string) => {
    setDrafts((prev) => prev.filter((d) => d.id !== draftId));
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
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
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>hub</span>
              Đồ thị
            </Link>
          </div>
        }
      />

      <div className="flex-1 flex gap-0 -mx-6 md:-mx-8 lg:-mx-10 -mb-6 md:-mb-8 lg:-mb-10 min-h-0 border-t border-border overflow-hidden">
        {/* Left: Page Tree */}
        <WikiPageTree
          activeSlug={fullSlug}
          pagesUrl={isScoped ? `/api/projects/${scopeId}/wiki?limit=200` : undefined}
          linkQueryParams={isScoped ? `?scopeType=${scopeType}&scopeId=${scopeId}` : undefined}
        />

        {/* Center: Content */}
        <div className="flex-1 overflow-y-auto min-w-0">
          {loading ? (
            <div className="max-w-3xl mx-auto px-8 py-8">
              <div className="flex items-center gap-2 mb-4">
                <div className="h-4 w-16 rounded bg-muted animate-pulse" />
                <div className="h-4 w-4 text-muted-foreground">/</div>
                <div className="h-4 w-24 rounded bg-muted animate-pulse" />
              </div>
              <div className="h-10 w-2/3 rounded-lg bg-muted animate-pulse mb-3" />
              <div className="h-4 w-full rounded bg-muted animate-pulse mb-2" />
              <div className="h-4 w-5/6 rounded bg-muted animate-pulse mb-8" />
              <div className="space-y-3">
                {Array.from({ length: 8 }).map((_, i) => (
                  <div
                    key={i}
                    className="h-4 rounded bg-muted animate-pulse"
                    style={{ width: `${85 - i * 5}%`, opacity: 1 - i * 0.08 }}
                  />
                ))}
              </div>
            </div>
          ) : notFound ? (
            <div className="px-8 py-12">
              <EmptyState
                icon="find_in_page"
                title="Không tìm thấy trang"
                description={`Không tìm thấy trang wiki "${fullSlug}". Có thể trang chưa được biên dịch.`}
              />
            </div>
          ) : page ? (
            <div className="max-w-3xl mx-auto px-8 py-8">
              {/* Breadcrumb & Back Button */}
              <div className="flex items-center gap-3 mb-6">
                <Link
                  href={isScoped ? `/admin/workspaces` : "/admin/wiki"}
                  className="flex items-center justify-center w-8 h-8 rounded-full border border-border bg-background text-muted-foreground hover:bg-accent hover:text-foreground transition-colors shrink-0 shadow-sm"
                  title={isScoped ? "Quay lại không gian" : "Quay lại Wiki"}
                >
                  <span className="material-symbols-outlined text-[18px]">arrow_back</span>
                </Link>

                <nav className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Link
                    href={isScoped ? `/admin/workspaces` : "/admin/wiki"}
                    className="hover:text-foreground transition-colors font-medium"
                  >
                    {isScoped ? "Không gian" : "Wiki"}
                  </Link>
                  <span className="material-symbols-outlined text-muted-foreground/50" style={{ fontSize: 14 }}>chevron_right</span>
                  <span className="capitalize font-medium">
                    {wikiTypeGroupLabel(page.page_type)}
                  </span>
                  <span className="material-symbols-outlined text-muted-foreground/50" style={{ fontSize: 14 }}>chevron_right</span>
                  <span className="text-foreground font-semibold truncate max-w-[200px]">
                    {page.title}
                  </span>
                </nav>
              </div>

              {/* Page header + Edit button */}
              <div className="flex items-start justify-between gap-4 mb-8">
                <div className="flex-1 min-w-0">
                  <h1 className="font-heading text-4xl font-normal leading-tight text-foreground">
                    {page.title}
                  </h1>
                  {page.summary && (
                    <p className="mt-2 text-muted-foreground text-sm leading-6">{page.summary}</p>
                  )}
                </div>

                {mode === "view" && (canEdit || canPropose) && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setMode("edit")}
                    className="shrink-0 gap-1.5 mt-1"
                  >
                    <span className="material-symbols-outlined text-sm">edit</span>
                    {canEdit ? "Sửa" : "Đề xuất sửa"}
                  </Button>
                )}
              </div>

              {/* Draft review banner (editors/admins, view mode only) */}
              {mode === "view" && canReview && drafts.length > 0 && (
                <div className="mb-6">
                  <WikiDraftBanner
                    drafts={drafts}
                    onApproved={handleDraftApproved}
                    onRejected={handleDraftRejected}
                  />
                </div>
              )}

              {/* Markdown body or Editor */}
              {mode === "edit" ? (
                <WikiEditor
                  initialContent={page.content_md}
                  noteLabel={canEdit ? "Ghi chú thay đổi" : "Ghi chú đề xuất"}
                  notePlaceholder={
                    canEdit
                      ? "Mô tả ngắn gọn nội dung đã thay đổi (tuỳ chọn)"
                      : "Mô tả nội dung đề xuất thay đổi (tuỳ chọn)"
                  }
                  saveLabel={canEdit ? "Lưu thay đổi" : "Gửi đề xuất"}
                  onSave={canEdit ? handleSaveEdit : handleSaveProposal}
                  onCancel={() => setMode("view")}
                />
              ) : (
                <WikiContent markdown={page.content_md} />
              )}
            </div>
          ) : null}
        </div>

        {/* Right: Sidebar (hidden on < lg, only in view mode) */}
        {page && mode === "view" && (
          <div className="hidden lg:block h-full">
            <WikiSidebarRight slug={fullSlug} page={page} />
          </div>
        )}
      </div>

      <WikiSearchDialog open={searchOpen} onOpenChange={setSearchOpen} />
    </>
  );
}
