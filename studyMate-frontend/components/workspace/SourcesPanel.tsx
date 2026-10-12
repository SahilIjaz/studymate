"use client";

import { Quote, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef } from "react";
import type { Citation, Message } from "@/lib/api";
import { useMediaQuery } from "@/lib/media";
import { useStore } from "@/lib/store";
import { cn, pageLabel, truncate } from "@/lib/utils";
import { IconButton } from "../ui/Button";

export function SourcesPanel({ className }: { className?: string }) {
  const messages = useStore((s) => s.messages);
  const selected = useStore((s) => s.selectedCitation);
  const select = useStore((s) => s.selectCitation);
  const setOpen = useStore((s) => s.setSourcesOpen);
  const setDrawer = useStore((s) => s.setSourcesDrawer);
  const isWide = useMediaQuery("(min-width: 1280px)");
  const retrievalQuery = useStore((s) => s.retrievalQuery);
  const streaming = useStore((s) => s.streaming);

  // Show the sources of the selected message, else the latest answer that has any.
  const focus = useMemo<Message | null>(() => {
    if (selected) return messages.find((m) => m.id === selected.messageId) ?? null;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant" && messages[i].citations.length) return messages[i];
    }
    return null;
  }, [messages, selected]);

  const question = useMemo(() => {
    if (!focus) return null;
    const index = messages.findIndex((m) => m.id === focus.id);
    for (let i = index - 1; i >= 0; i--) if (messages[i].role === "user") return messages[i].content;
    return null;
  }, [messages, focus]);

  const citations = focus?.citations ?? [];
  const isLatest = focus === messages[messages.length - 1];
  const showQuery = isLatest && retrievalQuery && question && retrievalQuery.trim() !== question.trim();

  return (
    <aside className={cn("flex h-full flex-col bg-bg-2/70", className)}>
      <div className="flex h-14 items-center justify-between px-4">
        <h2 className="flex items-center gap-2 text-sm font-medium">
          <Quote size={15} className="text-ink-3" /> Sources
          {citations.length > 0 && (
            <span className="tabular rounded-full bg-surface-3 px-1.5 py-0.5 font-mono text-[11px] text-ink-2">
              {citations.length}
            </span>
          )}
        </h2>
        <IconButton label="Hide sources" onClick={() => (isWide ? setOpen(false) : setDrawer(false))}>
          <X size={17} />
        </IconButton>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-4">
        {showQuery && (
          <p className="mb-3 rounded-xl bg-surface-2 px-3 py-2 text-[12px] leading-snug text-ink-3 ring-1 ring-border">
            Searched for <span className="text-ink">“{retrievalQuery}”</span>
          </p>
        )}

        {citations.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-4 pb-16 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-surface-3 text-ink-3 ring-1 ring-border">
              <Quote size={20} />
            </div>
            <p className="text-sm font-medium">
              {streaming ? "Finding passages…" : "Passages behind each answer appear here"}
            </p>
            <p className="max-w-[24ch] text-[12.5px] leading-snug text-ink-3">
              Click a numbered mark in an answer to jump to the exact page it came from.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <AnimatePresence initial={false}>
              {citations.map((c, i) => (
                <SourceCard
                  key={`${focus?.id}-${c.n}`}
                  citation={c}
                  index={i}
                  active={selected?.messageId === focus?.id && selected?.n === c.n}
                  onClick={() =>
                    select(selected?.messageId === focus?.id && selected?.n === c.n ? null : { messageId: focus!.id, n: c.n })
                  }
                />
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </aside>
  );
}

function SourceCard({
  citation,
  index,
  active,
  onClick,
}: {
  citation: Citation;
  index: number;
  active: boolean;
  onClick: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [active]);

  return (
    <motion.div
      ref={ref}
      layout
      initial={{ opacity: 0, x: 12 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0 }}
      transition={{ delay: index * 0.05, type: "spring", stiffness: 380, damping: 30 }}
      className={cn(
        "paper cursor-pointer rounded-2xl p-3 transition-colors",
        active ? "border-accent-strong ring-1 ring-accent-strong" : "hover:border-border-strong",
      )}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      aria-expanded={active}
    >
      <div className="flex items-start gap-2.5">
        <span
          className={cn(
            "flex h-6 min-w-6 items-center justify-center rounded-md px-1 font-mono text-[12px] font-medium",
            active ? "bg-accent text-accent-ink" : "bg-mark text-mark-ink",
          )}
        >
          {citation.n}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium leading-snug" title={citation.filename}>
            {citation.filename}
          </p>
          <p className="tabular flex items-center gap-2 text-[11.5px] text-ink-3">
            <span>{pageLabel(citation.page_start, citation.page_end)}</span>
            <span aria-hidden="true">·</span>
            <span className="flex items-center gap-1.5" title="Relevance relative to the best match">
              <span className="h-1 w-10 overflow-hidden rounded-full bg-surface-3">
                <span className="block h-full rounded-full bg-accent-strong" style={{ width: `${Math.round(citation.score * 100)}%` }} />
              </span>
              {Math.round(citation.score * 100)}%
            </span>
          </p>
        </div>
      </div>
      <AnimatePresence initial={false}>
        {active ? (
          <motion.blockquote
            key="full"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <p className="mt-3 whitespace-pre-wrap border-l-2 border-accent pl-3 font-display text-[13.5px] leading-relaxed text-ink-2">
              {citation.text}
            </p>
          </motion.blockquote>
        ) : (
          <motion.p key="short" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-2 text-[12.5px] leading-snug text-ink-3">
            {truncate(citation.text, 150)}
          </motion.p>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
