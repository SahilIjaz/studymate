"use client";

import { AlertTriangle, Check, FileText, Loader2, Trash2 } from "lucide-react";
import { motion } from "motion/react";
import type { Doc } from "@/lib/api";
import { type UploadState, useStore } from "@/lib/store";
import { cn, formatBytes } from "@/lib/utils";

export function DocumentCard({ doc }: { doc: Doc }) {
  const scope = useStore((s) => s.scope);
  const toggleScope = useStore((s) => s.toggleScope);
  const remove = useStore((s) => s.deleteDocument);
  const inScope = scope.includes(doc.id);
  const ready = doc.status === "ready";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -12, transition: { duration: 0.15 } }}
      className={cn(
        "group relative flex items-start gap-2.5 rounded-xl border px-2.5 py-2 transition-colors",
        inScope ? "border-accent-strong/60 bg-accent-soft" : "border-transparent hover:bg-surface-2",
      )}
    >
      <button
        type="button"
        disabled={!ready}
        onClick={() => toggleScope(doc.id)}
        aria-pressed={inScope}
        aria-label={inScope ? `Stop limiting questions to ${doc.filename}` : `Limit questions to ${doc.filename}`}
        title={ready ? (inScope ? "In scope · click to remove" : "Click to ask only this document") : undefined}
        className={cn(
          "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ring-1 transition-colors",
          inScope ? "bg-accent text-accent-ink ring-accent-strong" : "bg-surface-3 text-ink-2 ring-border",
          !ready && "opacity-60",
        )}
      >
        {doc.status === "processing" ? (
          <Loader2 size={15} className="animate-spin" />
        ) : doc.status === "failed" ? (
          <AlertTriangle size={15} className="text-danger" />
        ) : inScope ? (
          <Check size={15} strokeWidth={2.5} />
        ) : (
          <FileText size={15} />
        )}
      </button>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium leading-snug" title={doc.filename}>
          {doc.filename}
        </p>
        <p className="tabular text-[11.5px] text-ink-3">
          {doc.status === "processing" && "Indexing…"}
          {doc.status === "ready" && `${doc.page_count} page${doc.page_count === 1 ? "" : "s"} · ${doc.chunk_count} passages`}
          {doc.status === "failed" && <span className="text-danger">{doc.error ?? "Failed"}</span>}
        </p>
        {doc.status === "processing" && (
          <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-surface-3">
            <div className="shimmer h-full w-full" />
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={() => remove(doc.id)}
        aria-label={`Delete ${doc.filename}`}
        className="absolute right-1.5 top-1.5 rounded-md p-1 text-ink-4 opacity-0 transition hover:bg-surface-3 hover:text-danger focus-visible:opacity-100 group-hover:opacity-100"
      >
        <Trash2 size={13} />
      </button>
      <span className="sr-only">{formatBytes(doc.size_bytes)}</span>
    </motion.div>
  );
}

export function UploadRow({ upload }: { upload: UploadState }) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className="flex items-start gap-2.5 rounded-xl px-2.5 py-2"
    >
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface-3 text-ink-2 ring-1 ring-border">
        <Loader2 size={15} className="animate-spin" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium leading-snug">{upload.filename}</p>
        <p className="tabular text-[11.5px] text-ink-3">
          {upload.error ? <span className="text-danger">{upload.error}</span> : `Uploading · ${Math.round(upload.progress * 100)}%`}
        </p>
        {!upload.error && (
          <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-surface-3">
            <motion.div
              className="h-full rounded-full bg-accent-strong"
              initial={{ width: 0 }}
              animate={{ width: `${Math.max(4, upload.progress * 100)}%` }}
              transition={{ ease: "easeOut", duration: 0.2 }}
            />
          </div>
        )}
      </div>
    </motion.div>
  );
}
