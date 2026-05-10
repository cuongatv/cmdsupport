"use client";

import { useState, useEffect, useCallback } from "react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle,
  DialogTrigger,
  DialogFooter
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { AddTagsDialog } from "./add-tags-dialog";

type TagListResponse = {
  items: string[];
  total: number;
};

type TagsManagerDialogProps = {
  onUpdate?: () => void;
};

export function TagsManagerDialog({ onUpdate }: TagsManagerDialogProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [tags, setTags] = useState<string[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  
  const [search, setSearch] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);

  const loadTags = useCallback(async () => {
    setLoading(true);

    try {
      const params = new URLSearchParams();
      if (search) params.set("q", search);
      params.set("limit", "1000"); // Load everything

      const data = await api<TagListResponse>(`/api/tags?${params.toString()}`);
      
      setTags(data.items);
      setTotal(data.total);
      setSelectedTags([]); // Reset selection on search/reload
    } catch {
      setTags([]);
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => {
        loadTags();
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [isOpen, search]);

  const toggleSelectAll = () => {
    if (selectedTags.length === tags.length && tags.length > 0) {
      setSelectedTags([]);
    } else {
      setSelectedTags([...tags]);
    }
  };

  const toggleTag = (t: string) => {
    if (selectedTags.includes(t)) {
      setSelectedTags(selectedTags.filter(item => item !== t));
    } else {
      setSelectedTags([...selectedTags, t]);
    }
  };

  const handleDelete = async () => {
    if (selectedTags.length === 0) return;
    if (!confirm(`Bạn có chắc muốn xoá ${selectedTags.length} tag?`)) return;

    try {
      await api("/api/tags/bulk", {
        method: "DELETE",
        body: { names: selectedTags }
      });
      loadTags();
      if (onUpdate) onUpdate();
    } catch (error) {
      const msg = error instanceof ApiError ? (error.data as any)?.detail || error.message : "Unknown error";
      alert("Xoá tag thất bại: " + msg);
    }
  };

  const isAllSelected = tags.length > 0 && selectedTags.length === tags.length;

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger 
        render={
          <Button variant="outline" className="shadow-sahara border-primary/20 hover:border-primary/50 text-primary">
            <span className="material-symbols-outlined text-base mr-1">sell</span>
            Quản lý Tag
          </Button>
        }
      />
      <DialogContent className="sm:max-w-[550px] flex flex-col max-h-[85vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="material-symbols-outlined text-primary">sell</span>
            Quản lý Tag
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-4 flex-1 overflow-hidden">
          {/* Header Controls */}
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">search</span>
              <Input 
                placeholder="Tìm kiếm tag..." 
                className="pl-8 h-9 text-sm"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <AddTagsDialog onTagsAdded={() => {
              loadTags();
              if (onUpdate) onUpdate();
            }} />
          </div>

          {/* List Area */}
          <div className="flex-1 flex flex-col border border-border rounded-lg bg-secondary/5 overflow-hidden">
            <div className="flex items-center justify-between p-3 border-b border-border bg-background/50">
              <div className="flex items-center gap-2">
                <input 
                  type="checkbox" 
                  className="w-4 h-4 cursor-pointer"
                  checked={isAllSelected}
                  onChange={toggleSelectAll}
                />
                <span className="text-xs font-medium text-muted-foreground uppercase">
                  {isAllSelected ? "Bỏ chọn tất cả" : "Chọn tất cả"}
                </span>
              </div>
              <span className="text-[10px] text-muted-foreground">
                Đã chọn {selectedTags.length} / {total}
              </span>
            </div>

            <div className="flex-1 overflow-y-auto p-1 grid grid-cols-2 gap-1 content-start">
              {loading ? (
                <div className="col-span-2 py-10 flex justify-center">
                  <span className="material-symbols-outlined animate-spin text-muted-foreground">progress_activity</span>
                </div>
              ) : tags.length === 0 ? (
                <div className="col-span-2 py-10 text-center text-xs text-muted-foreground italic">
                  Không tìm thấy tag.
                </div>
              ) : (
                <>
                  {tags.map(t => (
                    <div 
                      key={t}
                      onClick={() => toggleTag(t)}
                      className={cn(
                        "flex items-center gap-2 p-2 rounded-md hover:bg-secondary/20 cursor-pointer transition-colors",
                        selectedTags.includes(t) && "bg-primary/5 border-primary/20"
                      )}
                    >
                      <input 
                        type="checkbox" 
                        className="w-3.5 h-3.5 cursor-pointer"
                        checked={selectedTags.includes(t)}
                        readOnly
                      />
                      <span className="text-xs truncate">{t}</span>
                    </div>
                  ))}
                </>
              )}
            </div>
          </div>
        </div>

        <DialogFooter className="border-t border-border pt-4 sm:justify-between flex items-center">
          <p className="text-[10px] text-muted-foreground italic">
            * Các tag đã chọn sẽ bị xoá vĩnh viễn.
          </p>
          <Button 
            variant="destructive" 
            size="sm" 
            disabled={selectedTags.length === 0}
            onClick={handleDelete}
            className="h-8 px-4"
          >
            <span className="material-symbols-outlined text-sm mr-1">delete</span>
            Xoá ({selectedTags.length})
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
