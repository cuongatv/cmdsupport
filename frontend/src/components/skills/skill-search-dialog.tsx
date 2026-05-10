"use client";

import React from "react";
import { api } from "@/lib/api";
import { Skill } from "@/components/skills/skill-card";
import { Dialog, DialogContent } from "@/components/ui/dialog";

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = React.useState(value);
  React.useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

export function SkillSearchDialog({
  open,
  onOpenChange,
  onSelect,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onSelect?: (skill: Skill) => void;
}) {
  const [skills, setSkills] = React.useState<Skill[]>([]);
  const [query, setQuery] = React.useState("");
  const inputRef = React.useRef<HTMLInputElement>(null);
  const debouncedQuery = useDebounce(query, 120);

  React.useEffect(() => {
    if (!open) return;
    api<{ items: Skill[] }>("/api/skills?limit=1000")
      .then((d) => setSkills(Array.isArray(d.items) ? d.items : []))
      .catch(() => setSkills([]));
  }, [open]);

  React.useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQuery("");
    }
  }, [open]);

  const filtered = React.useMemo(() => {
    if (!debouncedQuery) return skills;
    const q = debouncedQuery.toLowerCase();
    return skills.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        (s.description && s.description.toLowerCase().includes(q))
    );
  }, [skills, debouncedQuery]);

  const handleSelect = (skill: Skill) => {
    if (onSelect) {
      onSelect(skill);
    }
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg p-0 overflow-hidden gap-0 bg-background/95 backdrop-blur-xl border-border/50 shadow-2xl">
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-4 border-b border-border/50">
          <span className="material-symbols-outlined text-primary text-xl">
            search
          </span>
          <input
            ref={inputRef}
            type="text"
            placeholder="Tìm kiếm AI Skills theo tên, mô tả hoặc tag..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") onOpenChange(false);
            }}
            className="flex-1 text-sm bg-transparent outline-none text-foreground placeholder:text-muted-foreground font-manrope"
          />
          {query && (
            <button onClick={() => setQuery("")} className="text-muted-foreground hover:text-foreground transition-colors">
              <span className="material-symbols-outlined text-base">close</span>
            </button>
          )}
        </div>

        {/* Results */}
        <div className="max-h-[400px] overflow-y-auto py-2 custom-scrollbar">
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
              <span className="material-symbols-outlined text-4xl text-muted-foreground/30 mb-3">
                search_off
              </span>
              <p className="text-sm text-muted-foreground">
                {query ? `Không tìm thấy skill phù hợp "${query}"` : "Không có skill nào."}
              </p>
            </div>
          ) : (
            <div className="flex flex-col">
              <div className="px-4 py-2">
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">
                  Kết quả ({filtered.length})
                </span>
              </div>
              {filtered.slice(0, 50).map((skill) => (
                <button
                  key={skill.id}
                  onClick={() => handleSelect(skill)}
                  className="w-full flex items-start gap-4 px-4 py-3 hover:bg-primary/5 transition-all text-left group border-l-2 border-transparent hover:border-primary"
                >
                  <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0 group-hover:scale-110 transition-transform">
                    <span className="material-symbols-outlined text-primary text-xl">bolt</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-bold text-foreground group-hover:text-primary transition-colors truncate">
                        {skill.name}
                      </p>
                      {skill.department_names && skill.department_names.length > 0 && (
                        <span className="text-[10px] bg-secondary px-2 py-0.5 rounded text-secondary-foreground font-medium">
                          {skill.department_names[0]}
                        </span>
                      )}
                    </div>
                    {skill.description && (
                      <p className="text-xs text-muted-foreground truncate mt-0.5 line-clamp-1">
                        {skill.description}
                      </p>
                    )}
                    </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Footer info */}
        <div className="border-t border-border/50 px-4 py-3 flex items-center gap-4 text-[10px] text-muted-foreground bg-secondary/10">
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 rounded border border-border bg-background font-mono text-[9px] shadow-sm">↵</kbd>
            chọn
          </span>
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 rounded border border-border bg-background font-mono text-[9px] shadow-sm">↑↓</kbd>
            di chuyển
          </span>
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 rounded border border-border bg-background font-mono text-[9px] shadow-sm">Esc</kbd>
            đóng
          </span>
        </div>
      </DialogContent>
    </Dialog>
  );
}
