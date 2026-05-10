"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { 
  Dialog, 
  DialogContent, 
  DialogDescription, 
  DialogFooter, 
  DialogHeader, 
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type AddTagsDialogProps = {
  onTagsAdded: () => void;
};

export function AddTagsDialog({ onTagsAdded }: AddTagsDialogProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [inputValue, setInputValue] = useState("");

  const handleSave = async () => {
    if (!inputValue.trim()) return;

    try {
      setLoading(true);
      const tagNames = inputValue.split(",").map(t => t.trim()).filter(Boolean);
      
      await api("/api/tags/bulk", {
        method: "POST",
        body: { names: tagNames }
      });

      setIsOpen(false);
      setInputValue("");
      onTagsAdded();
    } catch (error) {
      const msg = error instanceof ApiError ? (error.data as any)?.detail || error.message : "Unknown error";
      alert("Thêm tag thất bại: " + msg);
    } finally {
      setLoading(false);
    }
  };

  // Only allow: a-z, A-Z, 0-9, _, -, ,, and space
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    const filtered = val.replace(/[^a-zA-Z0-9_\- ,]/g, "");
    setInputValue(filtered);
  };

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger 
        render={
          <Button className="h-8 bg-primary text-primary-foreground hover:bg-primary/90 shadow-sahara">
            <span className="material-symbols-outlined text-sm mr-1">add</span>
            Thêm Tag
          </Button>
        }
      />
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>Thêm Tag mới</DialogTitle>
          <DialogDescription>
            Nhập tên tag, phân cách bằng dấu phẩy (ví dụ: ai, bot, tool-1).
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          <Label htmlFor="tag-input">Tên Tag</Label>
          <Input 
            id="tag-input"
            placeholder="tag1, tag2, tag3..."
            value={inputValue}
            onChange={handleChange}
            className="mt-2"
            autoFocus
          />
          <p className="text-[10px] text-muted-foreground mt-2 italic">
            * Ký tự cho phép: chữ cái, số, dấu gạch dưới, gạch ngang và dấu phẩy.
          </p>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => setIsOpen(false)}>Huỷ</Button>
          <Button disabled={loading || !inputValue.trim()} onClick={handleSave}>
            {loading ? "Đang lưu..." : "Lưu Tag"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
