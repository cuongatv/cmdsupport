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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type BulkAddTagsToSkillsDialogProps = {
  skillIds: string[];
  allTags: string[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
};

export function BulkAddTagsToSkillsDialog({ 
  skillIds, 
  allTags,
  open, 
  onOpenChange, 
  onSuccess 
}: BulkAddTagsToSkillsDialogProps) {
  const [loading, setLoading] = useState(false);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSave = async () => {
    if (selectedTags.length === 0 || skillIds.length === 0) return;

    try {
      setLoading(true);
      
      await api("/api/skills/bulk/tags", {
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
      const msg = error instanceof ApiError ? (error.data as any)?.detail || error.message : "Unknown error";
      alert("Thêm tag cho skill thất bại: " + msg);
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

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      const val = tagInput.trim().toLowerCase();
      // Allow adding new tags or selecting existing ones
      if (val && !selectedTags.includes(val)) {
        setSelectedTags([...selectedTags, val]);
        setTagInput("");
      }
    } else if (e.key === "Backspace" && !tagInput && selectedTags.length > 0) {
      setSelectedTags(selectedTags.slice(0, -1));
    }
  };

  const filteredSuggestions = useMemo(() => {
    if (!tagInput) return [];
    return allTags.filter(t => 
      t.toLowerCase().includes(tagInput.toLowerCase()) && 
      !selectedTags.includes(t)
    ).slice(0, 5);
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
          <DialogTitle>Thêm Tag cho {skillIds.length} Skill</DialogTitle>
          <DialogDescription>
            Nhập hoặc chọn tag. Các tag này sẽ được thêm vào tất cả skill đã chọn.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 grid gap-2 relative">
          <Label>Tag</Label>
          <div 
            className={cn(
              "flex flex-wrap gap-1.5 p-2 min-h-[42px] border border-border rounded-md bg-secondary/5 transition-all cursor-text",
              "focus-within:border-primary focus-within:ring-1 focus-within:ring-primary/20 focus-within:bg-background"
            )}
            onClick={() => inputRef.current?.focus()}
          >
            {selectedTags.map(t => (
              <Badge 
                key={t}
                variant="secondary" 
                className="pl-2 pr-1.5 py-0.5 h-7 text-[12px] font-medium border-primary/30 bg-primary/5 text-primary rounded-full flex items-center gap-1"
              >
                {t}
                <button 
                  type="button" 
                  onClick={(e) => { e.stopPropagation(); toggleTag(t); }}
                  className="w-4 h-4 rounded-full bg-primary/10 hover:bg-destructive hover:text-white transition-all flex items-center justify-center ml-0.5"
                >
                  <span className="material-symbols-outlined" style={{ fontSize: '8px' }}>close</span>
                </button>
              </Badge>
            ))}
            <input
              ref={inputRef}
              type="text"
              className="flex-1 bg-transparent border-none outline-none text-sm min-w-[120px] py-0.5"
              placeholder={selectedTags.length === 0 ? "Nhập để thêm hoặc tìm kiếm..." : ""}
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={handleKeyDown}
            />
          </div>

          {/* Suggestions Dropdown */}
          {filteredSuggestions.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-1 border border-border rounded-md bg-card shadow-xl z-20 overflow-hidden">
              {filteredSuggestions.map(t => (
                <div 
                  key={t}
                  onClick={() => toggleTag(t)}
                  className="px-3 py-2 text-sm hover:bg-primary/10 hover:text-primary cursor-pointer transition-colors"
                >
                  {t}
                </div>
              ))}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Huỷ</Button>
          <Button disabled={loading || selectedTags.length === 0} onClick={handleSave}>
            {loading ? "Đang thêm..." : "Thêm Tag"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
