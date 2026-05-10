"use client";

import { PublicTopBar } from "@/components/layout/public-top-bar";
import { PublicFooter } from "@/components/layout/public-footer";

export default function PublicLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex flex-col bg-background">
      <PublicTopBar />
      <main className="flex-1 flex flex-col">{children}</main>
      <PublicFooter />
    </div>
  );
}
