"use client";

import { ArrowUp, Square } from "lucide-react";
import { motion } from "motion/react";
import { useCallback, useEffect, useRef } from "react";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

const MAX_CHARS = 2000;

export function Composer({ disabledReason }: { disabledReason?: string | null }) {
  const draft = useStore((s) => s.draft);
  const setDraft = useStore((s) => s.setDraft);
  const ask = useStore((s) => s.ask);
  const stop = useStore((s) => s.stop);
  const streaming = useStore((s) => s.streaming);
  const scope = useStore((s) => s.scope);
  const documents = useStore((s) => s.documents);
  const ref = useRef<HTMLTextAreaElement>(null);

  const resize = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  useEffect(resize, [draft, resize]);
  useEffect(() => {
    if (!streaming) ref.current?.focus();
  }, [streaming]);

  const canSend = draft.trim().length > 0 && !streaming && !disabledReason;

  const submit = () => {
    if (!canSend) return;
    void ask(draft);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  const ready = documents.filter((d) => d.status === "ready");
  const scoped = scope.filter((id) => ready.some((d) => d.id === id));

  return (
    <div className="px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2 sm:px-6">
      <motion.div
        layout
        className={cn(
          "paper mx-auto flex max-w-3xl flex-col rounded-[22px] transition-shadow focus-within:border-border-strong focus-within:shadow-float",
        )}
      >
        <textarea
          id="composer"
          ref={ref}
          rows={1}
          value={draft}
          maxLength={MAX_CHARS}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={disabledReason ?? (ready.length ? "Ask anything about your documents…" : "Upload a PDF to start asking…")}
          disabled={Boolean(disabledReason)}
          aria-label="Your question"
          className="max-h-[200px] w-full resize-none bg-transparent px-4 pt-3.5 pb-1 text-[15px] leading-relaxed outline-none placeholder:text-ink-4 disabled:opacity-60"
        />
        <div className="flex items-center justify-between gap-2 px-2.5 pb-2.5">
          <div className="min-w-0 truncate pl-1.5 text-[12px] text-ink-3">
            {scoped.length > 0 ? (
              <span>
                Asking <span className="text-ink">{scoped.length}</span> of {ready.length} document{ready.length === 1 ? "" : "s"}
              </span>
            ) : ready.length > 1 ? (
              <span>Asking across all {ready.length} documents</span>
            ) : (
              <span className="hidden sm:inline">
                <kbd className="rounded border px-1 font-mono text-[10.5px]">Enter</kbd> to send ·{" "}
                <kbd className="rounded border px-1 font-mono text-[10.5px]">Shift</kbd>+
                <kbd className="rounded border px-1 font-mono text-[10.5px]">Enter</kbd> for a new line
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {draft.length > MAX_CHARS * 0.8 && (
              <span className="tabular text-[11px] text-ink-3">
                {draft.length}/{MAX_CHARS}
              </span>
            )}
            {streaming ? (
              <button
                type="button"
                onClick={stop}
                aria-label="Stop generating"
                className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-ink text-bg transition hover:opacity-90"
              >
                <Square size={13} fill="currentColor" />
              </button>
            ) : (
              <motion.button
                type="button"
                onClick={submit}
                disabled={!canSend}
                aria-label="Send"
                whileTap={{ scale: 0.92 }}
                className={cn(
                  "inline-flex h-9 w-9 items-center justify-center rounded-full transition-colors",
                  canSend ? "bg-accent text-accent-ink hover:bg-accent-strong" : "bg-surface-3 text-ink-4",
                )}
              >
                <ArrowUp size={17} strokeWidth={2.4} />
              </motion.button>
            )}
          </div>
        </div>
      </motion.div>
      <p className="mx-auto mt-2 max-w-3xl px-2 text-center text-[11.5px] text-ink-4">
        Answers come only from your uploaded PDFs. Every claim is cited to a page.
      </p>
    </div>
  );
}
