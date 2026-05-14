"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Sidebar } from "@/components/layout/sidebar";
import { MobileTopBar } from "@/components/layout/mobile-top-bar";
import { LoadingLogo } from "@/components/shared/loading-logo";
import { NotificationBadge } from "@/components/tasks/notification-badge";

export default function MeLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
  }, [user, loading, router]);

  // Close drawer on route change
  useEffect(() => {
    const id = window.setTimeout(() => setSidebarOpen(false), 0);
    return () => window.clearTimeout(id);
  }, [pathname]);

  // Close drawer on ESC
  useEffect(() => {
    if (!sidebarOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSidebarOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [sidebarOpen]);

  // Lock body scroll when drawer open
  useEffect(() => {
    if (sidebarOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [sidebarOpen]);

  const openDrawer = useCallback(() => setSidebarOpen(true), []);
  const closeDrawer = useCallback(() => setSidebarOpen(false), []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <LoadingLogo size="md" label="Đang tải…" />
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="h-screen flex flex-col lg:flex-row bg-background overflow-hidden">
      {/* Desktop sidebar — fixed left */}
      <div className="hidden lg:flex h-full shrink-0">
        <Sidebar />
      </div>

      {/* Mobile drawer overlay */}
      {sidebarOpen && (
        <div className="lg:hidden fixed inset-0 z-40" aria-hidden="true">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/40 transition-opacity"
            onClick={closeDrawer}
          />
          {/* Drawer panel */}
          <div className="absolute inset-y-0 left-0 z-50 w-[260px] shadow-xl">
            <Sidebar />
          </div>
        </div>
      )}

      {/* Main area */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden min-w-0">
        {/* Mobile top bar */}
        <MobileTopBar onMenuClick={openDrawer} />

        {/* Top action bar — notifications */}
        <header className="flex h-12 items-center justify-end gap-2 px-4 md:px-6 lg:px-10 border-b border-sidebar-border bg-background shrink-0">
          <NotificationBadge />
        </header>

        <main className="flex-1 flex flex-col overflow-hidden min-w-0">
          <div className="p-6 md:p-8 lg:p-10 pt-4! w-full flex-1 min-h-0 flex flex-col gap-8 overflow-y-auto">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
