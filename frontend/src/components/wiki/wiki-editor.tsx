"use client";

import React from "react";
import { WikiContent } from "./wiki-content";
import { Button } from "@/components/ui/button";

// ---------------------------------------------------------------------------
// Toolbar helpers
// ---------------------------------------------------------------------------

function insertWrap(
  ta: HTMLTextAreaElement,
  value: string,
  setValue: (v: string) => void,
  before: string,
  after = "",
  placeholder = "text"
) {
  const s = ta.selectionStart;
  const e = ta.selectionEnd;
  const sel = value.slice(s, e) || placeholder;
  const next = value.slice(0, s) + before + sel + after + value.slice(e);
  setValue(next);
  requestAnimationFrame(() => {
    ta.focus();
    ta.setSelectionRange(s + before.length, s + before.length + sel.length);
  });
}

function insertLinePrefix(
  ta: HTMLTextAreaElement,
  value: string,
  setValue: (v: string) => void,
  prefix: string
) {
  const s = ta.selectionStart;
  const lineStart = value.lastIndexOf("\n", s - 1) + 1;
  const next = value.slice(0, lineStart) + prefix + value.slice(lineStart);
  setValue(next);
  requestAnimationFrame(() => {
    ta.focus();
    const pos = s + prefix.length;
    ta.setSelectionRange(pos, pos);
  });
}

function insertBlock(
  ta: HTMLTextAreaElement,
  value: string,
  setValue: (v: string) => void,
  block: string,
  cursorOffset: number
) {
  const s = ta.selectionStart;
  const next = value.slice(0, s) + block + value.slice(s);
  setValue(next);
  requestAnimationFrame(() => {
    ta.focus();
    const pos = s + cursorOffset;
    ta.setSelectionRange(pos, pos);
  });
}

// ---------------------------------------------------------------------------
// ToolbarButton
// ---------------------------------------------------------------------------

function ToolbarButton({
  icon,
  label,
  onClick,
}: {
  icon: string;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={label}
      onClick={onClick}
      className="flex items-center justify-center w-7 h-7 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
    >
      <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
        {icon}
      </span>
    </button>
  );
}

function ToolbarSep() {
  return <span className="w-px h-4 bg-border mx-0.5 shrink-0" />;
}

// ---------------------------------------------------------------------------
// WikiEditor
// ---------------------------------------------------------------------------

export type WikiEditorProps = {
  initialContent: string;
  /** Label shown above the note field */
  noteLabel: string;
  notePlaceholder?: string;
  saveLabel: string;
  onSave: (content: string, note: string) => Promise<void>;
  onCancel: () => void;
};

export function WikiEditor({
  initialContent,
  noteLabel,
  notePlaceholder,
  saveLabel,
  onSave,
  onCancel,
}: WikiEditorProps) {
  const [content, setContent] = React.useState(initialContent);
  const [note, setNote] = React.useState("");
  const [tab, setTab] = React.useState<"edit" | "preview">("edit");
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const taRef = React.useRef<HTMLTextAreaElement>(null);

  // Toolbar action helpers bound to current textarea state
  const w = (before: string, after = "", placeholder = "text") => {
    const ta = taRef.current;
    if (!ta) return;
    insertWrap(ta, content, setContent, before, after, placeholder);
  };
  const lp = (prefix: string) => {
    const ta = taRef.current;
    if (!ta) return;
    insertLinePrefix(ta, content, setContent, prefix);
  };
  const blk = (block: string, offset: number) => {
    const ta = taRef.current;
    if (!ta) return;
    insertBlock(ta, content, setContent, block, offset);
  };

  const handleSave = async () => {
    if (!content.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await onSave(content, note);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-0 rounded-xl border border-border overflow-hidden shadow-sahara">
      {/* Header: tab toggle */}
      <div className="flex items-center justify-between px-3 py-2 bg-card border-b border-border">
        <div className="flex gap-1">
          {(["edit", "preview"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors capitalize ${
                tab === t
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent"
              }`}
            >
              {t === "edit" ? "Sửa" : "Xem trước"}
            </button>
          ))}
        </div>
        <span className="text-xs text-muted-foreground">Markdown</span>
      </div>

      {tab === "edit" ? (
        <>
          {/* Toolbar */}
          <div className="flex items-center flex-wrap gap-0.5 px-2 py-1.5 bg-card/60 border-b border-border">
            <ToolbarButton icon="format_bold" label="Bold (Ctrl+B)" onClick={() => w("**", "**", "bold text")} />
            <ToolbarButton icon="format_italic" label="Italic (Ctrl+I)" onClick={() => w("*", "*", "italic text")} />
            <ToolbarButton icon="code" label="Inline code" onClick={() => w("`", "`", "code")} />
            <ToolbarSep />
            <button
              type="button"
              title="Heading 2"
              onClick={() => lp("## ")}
              className="px-1.5 h-7 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors text-xs font-bold font-mono"
            >
              H2
            </button>
            <button
              type="button"
              title="Heading 3"
              onClick={() => lp("### ")}
              className="px-1.5 h-7 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors text-xs font-bold font-mono"
            >
              H3
            </button>
            <ToolbarSep />
            <ToolbarButton icon="format_list_bulleted" label="Bullet list" onClick={() => lp("- ")} />
            <ToolbarButton icon="format_list_numbered" label="Numbered list" onClick={() => lp("1. ")} />
            <ToolbarButton icon="format_quote" label="Blockquote" onClick={() => lp("> ")} />
            <ToolbarSep />
            <ToolbarButton icon="data_object" label="Code block" onClick={() => blk("\n```\n\n```\n", 5)} />
            <ToolbarButton icon="link" label="Link" onClick={() => w("[", "](url)", "link text")} />
            <ToolbarButton icon="horizontal_rule" label="Horizontal rule" onClick={() => blk("\n\n---\n\n", 6)} />
          </div>

          {/* Textarea */}
          <textarea
            ref={taRef}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="w-full min-h-[400px] resize-y p-4 font-mono text-sm leading-6 bg-background text-foreground focus:outline-none placeholder:text-muted-foreground"
            placeholder="Viết nội dung markdown tại đây..."
            spellCheck={false}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "b") {
                e.preventDefault();
                w("**", "**", "bold text");
              }
              if ((e.metaKey || e.ctrlKey) && e.key === "i") {
                e.preventDefault();
                w("*", "*", "italic text");
              }
            }}
          />
        </>
      ) : (
        <div className="min-h-[400px] p-6 bg-background overflow-y-auto">
          {content.trim() ? (
            <WikiContent markdown={content} />
          ) : (
            <p className="text-sm text-muted-foreground italic">Không có nội dung để xem trước.</p>
          )}
        </div>
      )}

      {/* Note field + actions */}
      <div className="flex flex-col gap-3 px-4 py-3 bg-card border-t border-border">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-muted-foreground">{noteLabel}</label>
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={notePlaceholder ?? "Tuỳ chọn — mô tả nội dung thay đổi"}
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 placeholder:text-muted-foreground"
          />
        </div>

        {error && (
          <p className="text-xs text-destructive">{error}</p>
        )}

        <div className="flex items-center justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onCancel} disabled={saving}>
            Huỷ
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={saving || !content.trim()}
            className="gap-1.5"
          >
            {saving ? (
              <>
                <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                Đang lưu…
              </>
            ) : (
              <>
                <span className="material-symbols-outlined text-sm">save</span>
                {saveLabel}
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
