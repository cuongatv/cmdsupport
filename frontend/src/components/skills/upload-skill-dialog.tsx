"use client";

import { useState, useRef, useMemo, useEffect } from "react";
import { apiUpload, api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
import { cn } from "@/lib/utils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";

type UploadSkillDialogProps = {
  allDepartments: { id: string; name: string }[];
  onUploaded: () => void;
};

export function UploadSkillDialog({ allDepartments, onUploaded }: UploadSkillDialogProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [uploadLoading, setUploadLoading] = useState(false);

  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null);
  const [scopeType, setScopeType] = useState("global");
  const [deptIds, setDeptIds] = useState<string[]>([]);
  const [force, setForce] = useState(false);
  const [conflictFiles, setConflictFiles] = useState<string[]>([]);

  const inputRef = useRef<HTMLInputElement>(null);

  const resetForm = () => {
    setSelectedFiles(null);
    setScopeType("global");
    setDeptIds([]);
    setForce(false);
    setConflictFiles([]);
  };

  const handleUpload = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!selectedFiles || selectedFiles.length === 0) return;

    try {
      setUploadLoading(true);
      const formData = new FormData();
      for (let i = 0; i < selectedFiles.length; i++) {
        formData.append("files", selectedFiles[i]);
      }
      formData.append("scope_type", scopeType);
      
      if (scopeType === "department" && deptIds.length > 0) {
        deptIds.forEach(id => {
          formData.append("department_ids", id);
        });
        formData.append("scope_id", deptIds[0]); // Legacy support
      }

      if (force) {
        formData.append("force", "true");
      }

      await apiUpload("/api/skills/upload", formData);
      onUploaded();
      setIsOpen(false);
      resetForm();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setConflictFiles((err.data as { detail?: { conflicts?: string[] } } | null)?.detail?.conflicts || []);
      } else {
        alert(err instanceof Error ? err.message : "Tải lên thất bại");
      }
    } finally {
      setUploadLoading(false);
    }
  };


  return (
    <Dialog open={isOpen} onOpenChange={(open) => {
      setIsOpen(open);
      if (!open) resetForm();
    }}>
      <DialogTrigger
        render={
          <Button className="bg-primary text-primary-foreground hover:bg-primary/90 shadow-sahara">
            <span className="material-symbols-outlined text-base mr-1">upload</span>
            Tải lên Skill
          </Button>
        }
      />
      <DialogContent className="sm:max-w-[500px]">
        <form onSubmit={handleUpload}>
          <DialogHeader>
            <DialogTitle className="text-2xl font-serif font-semibold tracking-tight text-foreground">Tải lên AI Skill</DialogTitle>
            <DialogDescription className="font-manrope">
              Chọn một hoặc nhiều gói ZIP chứa AI Skills.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-6 py-6">
            <div className="grid gap-2">
              <Label htmlFor="files">Gói Skill (ZIP)</Label>
              <Input
                id="files"
                type="file"
                accept=".zip"
                multiple
                onChange={(e) => setSelectedFiles(e.target.files)}
                className="cursor-pointer bg-secondary/5 border-dashed border-2 hover:border-primary/50 transition-all py-8 h-auto"
              />
              {selectedFiles && selectedFiles.length > 0 && (
                <p className="text-[11px] text-primary font-medium animate-in fade-in">
                  Đã chọn {selectedFiles.length} tệp
                </p>
              )}
            </div>

            <div className="grid gap-2">
              <Label>Phạm vi hiển thị</Label>
              <Select value={scopeType} onValueChange={(v) => {
                setScopeType(v || "global");
                setDeptIds([]);
              }}>
                <SelectTrigger className="bg-secondary/5 h-11">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-base text-muted-foreground">
                      {scopeType === "global" ? "public" : "corporate_fare"}
                    </span>
                    <span className="capitalize">
                      {scopeType === "global" ? "Toàn hệ thống" : "Đơn vị"}
                    </span>
                  </div>
                </SelectTrigger>
                <SelectContent className="min-w-[240px]">
                  <SelectItem value="global">
                    <div className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-base text-muted-foreground">public</span>
                      Toàn hệ thống (Tất cả đơn vị)
                    </div>
                  </SelectItem>
                  <SelectItem value="department">
                    <div className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-base text-muted-foreground">corporate_fare</span>
                      Đơn vị cụ thể
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {scopeType === "department" && (
              <div className="grid gap-2 animate-in fade-in slide-in-from-top-1">
                <Label>Đơn vị đích</Label>
                <div className="bg-secondary/5 rounded-xl border border-border p-3">
                  <div className="max-h-[200px] pr-4 overflow-y-auto custom-scrollbar">
                    <div className="grid grid-cols-1 gap-2">
                      {allDepartments.map((d) => (
                        <div key={d.id} className="flex items-center space-x-2 group/item">
                          <Checkbox 
                            id={`upload-dept-${d.id}`} 
                            checked={deptIds.includes(d.id)}
                            onCheckedChange={(checked) => {
                              if (checked) {
                                setDeptIds([...deptIds, d.id]);
                              } else {
                                setDeptIds(deptIds.filter(id => id !== d.id));
                              }
                            }}
                          />
                          <label
                            htmlFor={`upload-dept-${d.id}`}
                            className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer group-hover/item:text-primary transition-colors"
                          >
                            {d.name}
                          </label>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
            
              </div>
            )}


            {conflictFiles.length > 0 && (
              <div className="bg-destructive/5 border border-destructive/20 p-4 rounded-lg flex flex-col gap-2">
                <div className="flex items-center gap-2 text-destructive font-semibold text-sm">
                  <span className="material-symbols-outlined text-lg">warning</span>
                  Phát hiện tên trùng lặp
                </div>
                <p className="text-xs text-muted-foreground">
                  Skill đã tồn tại: {conflictFiles.join(", ")}. Ghi đè?
                </p>
                <div className="flex items-center gap-2 mt-2">
                  <input
                    type="checkbox"
                    id="force-check"
                    checked={force}
                    onChange={(e) => setForce(e.target.checked)}
                    className="w-4 h-4 cursor-pointer"
                  />
                  <Label htmlFor="force-check" className="text-xs cursor-pointer">Tôi xác nhận ghi đè</Label>
                </div>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button type="submit" disabled={uploadLoading || !selectedFiles || (conflictFiles.length > 0 && !force)}>
              {uploadLoading ? "Đang xử lý..." : "Bắt đầu tải lên"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
