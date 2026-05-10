"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from "@/components/ui/table";
import { SEGMENT_SHORT_LABEL } from "@/components/cmd-support/segment-select";

type AdviceSummary = {
  id: string;
  customer_name: string;
  province_name: string | null;
  industry_name: string | null;
  customer_segment: string | null;
  status: string;
  created_by_name: string;
  created_at: string;
};

type ListResponse = {
  items: AdviceSummary[];
  total: number;
  page: number;
  page_size: number;
};

const statusMap: Record<string, { label: string; variant: "secondary" | "destructive" }> = {
  ready: { label: "Sẵn sàng", variant: "secondary" },
  failed: { label: "Lỗi", variant: "destructive" },
};

export default function CmdSupportHistoryPage() {
  const router = useRouter();
  const [data, setData] = useState<ListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const pageSize = 20;

  useEffect(() => {
    setLoading(true);
    api<ListResponse>(`/api/cmd-support/advice?page=${page}&page_size=${pageSize}`)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [page]);

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0;

  return (
    <>
      <PageHeader
        title="Lịch sử tư vấn"
        description="Danh sách các phiên tư vấn khách hàng doanh nghiệp."
      />

      {loading ? (
        <div className="flex items-center justify-center h-32">
          <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
            progress_activity
          </span>
        </div>
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          icon="history"
          title="Chưa có phiên tư vấn nào"
          description="Tạo phiên tư vấn mới tại trang Tư vấn KHDN."
          action={
            <Button onClick={() => router.push("/admin/cmd-support")}>
              Tư vấn KHDN
            </Button>
          }
        />
      ) : (
        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-card overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Khách hàng</TableHead>
                  <TableHead className="hidden sm:table-cell">Phân khúc</TableHead>
                  <TableHead className="hidden sm:table-cell">Tỉnh/TP</TableHead>
                  <TableHead className="hidden md:table-cell">Ngành nghề</TableHead>
                  <TableHead>Trạng thái</TableHead>
                  <TableHead className="hidden lg:table-cell">Người tạo</TableHead>
                  <TableHead>Thời gian</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((item) => {
                  const st = statusMap[item.status] ?? { label: item.status, variant: "secondary" as const };
                  return (
                    <TableRow
                      key={item.id}
                      className="cursor-pointer"
                      onClick={() => router.push(`/admin/cmd-support/${item.id}`)}
                    >
                      <TableCell className="font-medium">{item.customer_name}</TableCell>
                      <TableCell className="hidden sm:table-cell text-muted-foreground">
                        {item.customer_segment
                          ? SEGMENT_SHORT_LABEL[item.customer_segment] ?? item.customer_segment
                          : "—"}
                      </TableCell>
                      <TableCell className="hidden sm:table-cell text-muted-foreground">
                        {item.province_name || "—"}
                      </TableCell>
                      <TableCell className="hidden md:table-cell text-muted-foreground">
                        {item.industry_name || "—"}
                      </TableCell>
                      <TableCell>
                        <Badge variant={st.variant}>{st.label}</Badge>
                      </TableCell>
                      <TableCell className="hidden lg:table-cell text-muted-foreground">
                        {item.created_by_name}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {new Date(item.created_at).toLocaleDateString("vi-VN", {
                          day: "2-digit",
                          month: "2-digit",
                          year: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground">
                Trang {page}/{totalPages} · {data.total} kết quả
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  Trước
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Sau
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
