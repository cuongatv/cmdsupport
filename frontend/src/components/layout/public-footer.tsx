"use client";

import Link from "next/link";

export function PublicFooter() {
  return (
    <footer className="border-t border-border bg-secondary px-4 sm:px-6 lg:px-10 py-4">
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>&copy; CMD Support &mdash; Trợ lý tư vấn KHDN BIDV</span>
        <span className="text-center hidden md:inline">
          Kết quả tư vấn mang tính tham khảo. RM phải xác minh điều kiện theo quy định BIDV.
        </span>
        <Link
          href="/login"
          className="hover:text-foreground transition-colors"
        >
          Đăng nhập
        </Link>
      </div>
    </footer>
  );
}
