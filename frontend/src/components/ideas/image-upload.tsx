"use client";

import { useRef, useState } from "react";
import Image from "next/image";
import { cn } from "@/lib/utils";

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_IMAGES = 5;
const ACCEPT = "image/jpeg,image/png,image/webp,image/gif,image/heic,image/heif";

export type StagedImage = {
  id: string;
  file: File;
  previewUrl: string;
};

export function ImageUpload({
  images,
  onChange,
  disabled,
}: {
  images: StagedImage[];
  onChange: (next: StagedImage[]) => void;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setError(null);

    const next: StagedImage[] = [...images];
    for (const file of Array.from(files)) {
      if (next.length >= MAX_IMAGES) {
        setError(`Tối đa ${MAX_IMAGES} ảnh.`);
        break;
      }
      if (!file.type.startsWith("image/")) {
        setError("Chỉ chấp nhận tệp ảnh.");
        continue;
      }
      if (file.size > MAX_IMAGE_BYTES) {
        setError(`Ảnh "${file.name}" vượt quá 5MB.`);
        continue;
      }
      next.push({
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        file,
        previewUrl: URL.createObjectURL(file),
      });
    }
    onChange(next);
  };

  const remove = (id: string) => {
    const target = images.find((i) => i.id === id);
    if (target) URL.revokeObjectURL(target.previewUrl);
    onChange(images.filter((i) => i.id !== id));
  };

  const canAddMore = images.length < MAX_IMAGES;

  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {images.map((img) => (
          <div
            key={img.id}
            className="group relative aspect-square rounded-xl overflow-hidden border border-border bg-muted"
          >
            <Image
              src={img.previewUrl}
              alt={img.file.name}
              fill
              sizes="200px"
              className="object-cover"
              unoptimized
            />
            <button
              type="button"
              disabled={disabled}
              onClick={() => remove(img.id)}
              className="absolute top-1.5 right-1.5 w-7 h-7 rounded-full bg-foreground/70 text-background backdrop-blur-sm flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-destructive"
              title="Xóa ảnh"
            >
              <span className="material-symbols-outlined text-[16px]">close</span>
            </button>
            <div className="absolute bottom-0 inset-x-0 px-2 py-1 bg-gradient-to-t from-black/70 to-transparent text-[10px] text-white truncate">
              {img.file.name}
            </div>
          </div>
        ))}

        {canAddMore && (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              if (!disabled) setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              if (!disabled) handleFiles(e.dataTransfer.files);
            }}
            className={cn(
              "aspect-square rounded-xl border-2 border-dashed flex flex-col items-center justify-center gap-1.5 text-center px-3 py-3 cursor-pointer transition-all",
              dragging
                ? "border-primary bg-primary/[0.06]"
                : "border-border bg-muted/40 hover:border-primary/60 hover:bg-primary/[0.04]",
              disabled && "opacity-50 cursor-not-allowed"
            )}
            onClick={() => !disabled && inputRef.current?.click()}
          >
            <span
              className="material-symbols-outlined text-primary text-[28px]"
              style={{
                fontVariationSettings: "'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 28",
              }}
            >
              add_photo_alternate
            </span>
            <span className="text-xs font-medium text-foreground">
              Thêm ảnh
            </span>
            <span className="text-[10px] text-muted-foreground leading-tight">
              Kéo thả hoặc chạm
            </span>
            <div className="flex gap-1 mt-1">
              <button
                type="button"
                disabled={disabled}
                onClick={(e) => {
                  e.stopPropagation();
                  inputRef.current?.click();
                }}
                className="px-2 py-0.5 rounded-md bg-card border border-border text-[10px] font-medium text-muted-foreground hover:text-foreground hover:border-primary/40"
              >
                Thư mục
              </button>
              <button
                type="button"
                disabled={disabled}
                onClick={(e) => {
                  e.stopPropagation();
                  cameraRef.current?.click();
                }}
                className="px-2 py-0.5 rounded-md bg-card border border-border text-[10px] font-medium text-muted-foreground hover:text-foreground hover:border-primary/40"
              >
                Camera
              </button>
            </div>
          </div>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        multiple
        className="hidden"
        onChange={(e) => {
          handleFiles(e.target.files);
          e.target.value = "";
        }}
      />
      {/* Mobile camera capture */}
      <input
        ref={cameraRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={(e) => {
          handleFiles(e.target.files);
          e.target.value = "";
        }}
      />

      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
        <span>
          {images.length}/{MAX_IMAGES} ảnh · tối đa 5MB mỗi ảnh · JPG, PNG, WEBP, HEIC
        </span>
        {error && <span className="text-destructive">{error}</span>}
      </div>
    </div>
  );
}
