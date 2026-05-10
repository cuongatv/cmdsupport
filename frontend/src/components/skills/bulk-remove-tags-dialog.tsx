"use client";

import { useState, useRef, useMemo } from "react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { 
  Dialog, 
  DialogContent, 
  DialogDescription, 
  DialogFooter, 
  DialogHeader, 
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type BulkRemoveTagsDialogProps = {
  skillIds: string[];
  allTags: string[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
};

export function BulkRemoveTagsDialog({ 
  skillIds, 
  allTags,
  open, 
  onOpenChange, 
  onSuccess 
}: BulkRemoveTagsDialogProps) {
  const [loading, setLoading] = useState(false);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSave = async () => {
    if (selectedTags.length === 0 || skillIds.length === 0) return;

    try {
      setLoading(true);
      
      await api("/api/skills/bulk/tags/remove", {
        method: "POST",
        body: { 
          skill_ids: skillIds,
          tags: selectedTags 
        }
      });

      setSelectedTags([]);
      setTagInput("");
      onSuccess();
      onOpenChange(false);
    } catch (error) {
      const msg = error instanceof ApiError ? (error.data as { detail?: string } | null)?.detail || error.message : "Unknown error";
      alert("Gỡ tag khỏi skill thất bại: " + msg);
    } finally {
      setLoading(false);
    }
  };

  const toggleTag = (t: string) => {
    if (selectedTags.includes(t)) {
      setSelectedTags(selectedTags.filter(item => item !== t));
    } else {
      setSelectedTags([...selectedTags, t]);
      setTagInput("");
    }
  };

  const filteredSuggestions = useMemo(() => {
    if (!tagInput) return allTags.slice(0, 10); // Show some suggestions by default
    return allTags.filter(t => 
      t.toLowerCase().includes(tagInput.toLowerCase()) && 
      !selectedTags.includes(t)
    ).slice(0, 10);
  }, [allTags, tagInput, selectedTags]);

  return (
    <Dialog open={open} onOpenChange={(o) => {
      onOpenChange(o);
      if (!o) {
        setSelectedTags([]);
        setTagInput("");
      }
    }}>
      <DialogContent className="sm:max-w-[450px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className="material-symbols-outlined text-destructive">label_off</span>
            Gỡ Tag khỏi {skillIds.length} Skill
          </DialogTitle>
          <DialogDescription>
            Chọn các tag bạn muốn gỡ khỏi tất cả skill đã chọn.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 grid gap-2 relative">
          <Label>Tag đã chọn để gỡ</Label>
          <div 
            className={cn(
              "flex flex-wrap gap-1.5 p-2 min-h-[42px] border border-border rounded-md bg-secondary/5 transition-all cursor-text",
              "focus-within:border-destructive focus-within:ring-1 focus-within:ring-destructive/20 focus-within:bg-background"
            )}
            onClick={() => inputRef.current?.focus()}
          >
            {selectedTags.map(t => (
              <Badge 
                key={t}
                variant="secondary" 
                className="pl-2 pr-1.5 py-0.5 h-7 text-[12px] font-medium border-destructive/30 bg-destructive/5 text-destructive rounded-full flex items-center gap-1"
              >
                {t}
                <button 
                  type="button" 
                  onClick={(e) => { e.stopPropagation(); toggleTag(t); }}
                  className="w-4 h-4 rounded-full bg-destructive/10 hover:bg-destructive hover:text-white transition-all flex items-center justify-center ml-0.5"
                >
                  <span className="material-symbols-outlined" style={{ fontSize: '8px' }}>close</span>
                </button>
              </Badge>
            ))}
            <input
              ref={inputRef}
              type="text"
              className="flex-1 bg-transparent border-none outline-none text-sm min-w-[120px] py-0.5"
              placeholder={selectedTags.length === 0 ? "Nhập để tìm kiếm tag..." : ""}
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
            />
          </div>

          {/* Suggestions Dropdown */}
          {filteredSuggestions.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1 max-h-[120px] overflow-y-auto p-1 border border-border rounded-md">
              {filteredSuggestions.map(t => (
                <Badge
                  key={t}
                  variant="outline"
                  className={cn(
                    "cursor-pointer hover:bg-primary/10 transition-colors",
                    selectedTags.includes(t) && "bg-primary/20 border-primary"
                  )}
                  onClick={() => toggleTag(t)}
                >
                  {t}
                </Badge>
              ))}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Huỷ</Button>
          <Button 
            variant="destructive"
            disabled={loading || selectedTags.length === 0} 
            onClick={handleSave}
          >
            {loading ? "Đang gỡ..." : "Gỡ Tag"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
