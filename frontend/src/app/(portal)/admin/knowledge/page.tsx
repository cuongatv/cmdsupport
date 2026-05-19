"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { KnowledgeTable } from "@/components/knowledge/knowledge-table";
import { KnowledgeFilters } from "@/components/knowledge/knowledge-filters";
import { UploadDialog } from "@/components/knowledge/upload-dialog";
import { WikiReclassificationDialog } from "@/components/knowledge/wiki-reclassification-dialog";
import { KnowledgeTypeCards } from "@/components/types/knowledge-type-cards";
import { KnowledgeTypeDialog } from "@/components/types/knowledge-type-dialog";

export type KnowledgeType = {
  id: string;
  slug: string;
  name: string;
  color: string;
  description?: string;
  sort_order: number;
  source_count?: number;
};

export type Department = {
  id: string;
  name: string;
};

export type Source = {
  id: string;
  title: string;
  file_name?: string;
  source_type?: string;
  status: string;
  progress?: number;
  progress_message?: string;
  page_count?: number;
  wiki_page_count?: number;
  knowledge_type_id?: string;
  knowledge_type_name?: string;
  knowledge_type_color?: string;
  department_ids?: string[];
  department_names?: string[];
  contributed_by_name?: string;
  scope_type?: string;
  scope_id?: string;
  created_at: string;
  updated_at?: string;
};

type PaginatedSources = {
  items: Source[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export default function KnowledgePage() {
  const [activeTab, setActiveTab] = useState("documents");
  
  const [sources, setSources] = useState<Source[]>([]);
  const [types, setTypes] = useState<KnowledgeType[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [selectedDepartment, setSelectedDepartment] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const pageSize = 20;
  
  const [typeDialogOpen, setTypeDialogOpen] = useState(false);
  const [editType, setEditType] = useState<KnowledgeType | null>(null);
  const [reclassifyOpen, setReclassifyOpen] = useState(false);

  const loadSources = useCallback(async (silent = false, p = 1, s = "") => {
    if (!silent) setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(p),
        page_size: String(pageSize),
      });
      if (selectedType) {
        const matchedType = types.find((t) => t.slug === selectedType);
        if (matchedType) params.set("knowledge_type_id", matchedType.id);
      }
      if (selectedDepartment) params.set("department_id", selectedDepartment);
      if (s) params.set("search", s);

      const data = await api<PaginatedSources>(`/api/sources?${params}`);
      setSources(data.items);
      setTotal(data.total);
      setTotalPages(data.total_pages);
      setPage(data.page);
    } catch {
      if (!silent) setSources([]);
    } finally {
      if (!silent) setLoading(false);
    }
     
  }, [selectedType, selectedDepartment, types]);

  // Polling cho trạng thái tài liệu
  useEffect(() => {
    const hasPending = sources.some((s) => s.status === "pending" || s.status === "processing");
    if (!hasPending) return;

    const interval = setInterval(() => {
      loadSources(true, page, search);
    }, 3000);

    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sources, loadSources]);

  const loadMeta = useCallback(async () => {
    try {
      const [typesData, deptsData] = await Promise.all([
        api<KnowledgeType[]>("/api/knowledge-types"),
        api<Department[]>("/api/departments"),
      ]);
      setTypes(typesData);
      setDepartments(deptsData);
    } catch {
      setTypes([]);
      setDepartments([]);
    }
  }, []);

  useEffect(() => {
    loadMeta();
  }, [loadMeta]);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  const handleSearch = (q: string) => {
    setSearch(q);
    setPage(1);
    loadSources(false, 1, q);
  };

  const handlePageChange = (p: number) => {
    setPage(p);
    loadSources(false, p, search);
  };

  return (
    <>
      <PageHeader
        title="Kho tài liệu"
        description="Quản lý và tổ chức tài liệu, phân loại của tổ chức."
        action={
          activeTab === "documents" ? (
            <div className="flex items-center gap-2">
              <Button
                data-testid="open-reclassify-dialog"
                variant="outline"
                onClick={() => setReclassifyOpen(true)}
              >
                <span className="material-symbols-outlined text-base mr-1">rule</span>
                Phân loại lại Wiki
              </Button>
              <Button
                onClick={() => setUploadOpen(true)}
                className="bg-primary text-primary-foreground hover:bg-primary/90"
              >
                <span className="material-symbols-outlined text-base mr-1">add</span>
                Tải lên tài liệu
              </Button>
            </div>
          ) : (
            <Button
              onClick={() => { setEditType(null); setTypeDialogOpen(true); }}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              <span className="material-symbols-outlined text-base mr-1">add</span>
              Thêm phân loại
            </Button>
          )
        }
      />

      <div className="rounded-lg border border-primary/20 bg-secondary px-4 py-3 mb-4">
        <div className="flex items-start gap-2">
          <span className="material-symbols-outlined text-primary text-lg mt-0.5">info</span>
          <p className="text-sm text-foreground">
            Chỉ tải lên tài liệu nội bộ đã được phê duyệt. Tài liệu sẽ được index và sử dụng làm nguồn tri thức cho AI.
          </p>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="mb-6">
          <TabsTrigger value="documents" className="gap-2">
            <span className="material-symbols-outlined text-[18px]">files</span>
            Tài liệu
          </TabsTrigger>
          <TabsTrigger value="types" className="gap-2">
            <span className="material-symbols-outlined text-[18px]">category</span>
            Phân loại
          </TabsTrigger>
        </TabsList>

        <TabsContent value="documents" className="mt-0 outline-none">
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            <div className="lg:col-span-1">
              <KnowledgeFilters
                types={types}
                selectedType={selectedType}
                onSelectType={setSelectedType}
                departments={departments}
                selectedDepartment={selectedDepartment}
                onSelectDepartment={setSelectedDepartment}
              />
            </div>
            <div className="lg:col-span-3">
              <KnowledgeTable
                sources={sources}
                types={types}
                departments={departments}
                loading={loading}
                onRefresh={() => loadSources(false, page, search)}
                page={page}
                totalPages={totalPages}
                total={total}
                onPageChange={handlePageChange}
                search={search}
                onSearch={handleSearch}
              />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="types" className="mt-0 outline-none">
          <KnowledgeTypeCards
            types={types}
            loading={types.length === 0 && loading}
            onEdit={(t) => { setEditType(t); setTypeDialogOpen(true); }}
            onRefresh={loadMeta}
          />
        </TabsContent>
      </Tabs>

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        types={types}
        departments={departments}
        onUploaded={() => loadSources(false, page, search)}
      />

      <KnowledgeTypeDialog
        open={typeDialogOpen}
        onOpenChange={setTypeDialogOpen}
        knowledgeType={editType}
        onSaved={loadMeta}
      />

      <WikiReclassificationDialog
        open={reclassifyOpen}
        onOpenChange={setReclassifyOpen}
      />
    </>
  );
}
