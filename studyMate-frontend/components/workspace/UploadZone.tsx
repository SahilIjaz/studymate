"use client";

import { FileUp } from "lucide-react";
import { motion } from "motion/react";
import { useCallback, useRef, useState } from "react";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

export function UploadZone({ compact = false, className }: { compact?: boolean; className?: string }) {
  const upload = useStore((s) => s.upload);
  const documents = useStore((s) => s.documents);
  const toast = useStore((s) => s.toast);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const accept = useCallback(
    (list: FileList | File[]) => {
      const files = Array.from(list);
      const pdfs = files.filter((f) => f.name.toLowerCase().endsWith(".pdf") || f.type === "application/pdf");
      if (pdfs.length < files.length) toast({ kind: "error", title: "Only PDF files are supported" });
      if (pdfs.length) void upload(pdfs);
    },
    [upload, toast],
  );

  return (
    <motion.div
      role="button"
      tabIndex={0}
      aria-label="Upload PDF documents"
      onClick={() => inputRef.current?.click()}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          inputRef.current?.click();
        }
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        accept(e.dataTransfer.files);
      }}
      animate={dragging ? { scale: 1.02 } : { scale: 1 }}
      className={cn(
        "group relative flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border border-dashed text-center transition-colors",
        dragging ? "border-accent-strong bg-accent-soft" : "border-border-strong hover:border-ink-3 hover:bg-surface-2",
        compact ? "px-3 py-4" : "px-6 py-10",
        className,
      )}
    >
      <input
        ref={inputRef}
        id="file-input"
        type="file"
        accept="application/pdf,.pdf"
        multiple
        className="sr-only"
        onChange={(e) => {
          if (e.target.files) accept(e.target.files);
          e.target.value = "";
        }}
      />
      <motion.span
        animate={dragging ? { y: -4 } : { y: 0 }}
        className={cn(
          "flex items-center justify-center rounded-xl bg-surface-3 text-ink-2 ring-1 ring-border group-hover:text-ink",
          compact ? "h-9 w-9" : "h-12 w-12",
        )}
      >
        <FileUp size={compact ? 17 : 22} />
      </motion.span>
      <div>
        <p className={cn("font-medium", compact ? "text-[13px]" : "text-[15px]")}>
          {dragging ? "Drop to upload" : documents.length ? "Add another PDF" : "Drop a PDF here"}
        </p>
        <p className={cn("text-ink-3", compact ? "text-[11.5px]" : "text-[13px]")}>
          {compact ? "or click to browse" : "Lecture notes, textbooks, papers · up to 20 MB"}
        </p>
      </div>
    </motion.div>
  );
}
