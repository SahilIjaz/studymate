"use client";

import { Sparkles } from "lucide-react";
import { motion } from "motion/react";
import { useMemo } from "react";
import { useStore } from "@/lib/store";
import { UploadZone } from "./UploadZone";

const GENERIC = ["Summarize the main points of this document", "Explain the key terms with definitions", "What would an exam ask about this?"];

export function EmptyState() {
  const documents = useStore((s) => s.documents);
  const suggestions = useStore((s) => s.suggestions);
  const ask = useStore((s) => s.ask);
  const ready = documents.filter((d) => d.status === "ready");
  const indexing = documents.some((d) => d.status === "processing");

  const prompts = useMemo(() => {
    const specific = ready.flatMap((d) => suggestions[d.id] ?? []);
    const pool = specific.length ? specific : GENERIC;
    return pool.slice(0, 6);
  }, [ready, suggestions]);

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center px-4 py-10 text-center">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="w-full"
      >
        <p className="eyebrow mb-4">
          {ready.length ? `${ready.length} document${ready.length === 1 ? "" : "s"} ready` : "Your study desk"}
        </p>
        <h1 className="font-display text-[2rem] font-medium leading-[1.1] tracking-tight sm:text-[2.6rem]">
          {ready.length ? (
            <>
              What do you want to <span className="mark">understand</span> today?
            </>
          ) : (
            <>
              Start with a <span className="mark">PDF</span>.
            </>
          )}
        </h1>
        <p className="mx-auto mt-3 max-w-[44ch] text-[15px] text-ink-2">
          {ready.length
            ? "Ask in your own words. Every answer is built only from your documents and cites the page it came from."
            : indexing
              ? "Indexing your document. Questions unlock in a few seconds."
              : "Lecture slides, a textbook chapter, a paper. StudyMate reads it, then answers with page citations."}
        </p>

        {ready.length === 0 && !indexing ? (
          <UploadZone className="mt-8 bg-surface" />
        ) : (
          <div className="mt-8 flex flex-wrap justify-center gap-2">
            {prompts.map((p, i) => (
              <motion.button
                key={p}
                type="button"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15 + i * 0.05 }}
                whileHover={{ y: -2 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => ask(p)}
                disabled={!ready.length}
                className="paper inline-flex max-w-full items-center gap-2 rounded-full px-4 py-2 text-left text-[13.5px] text-ink-2 transition-colors hover:border-border-strong hover:text-ink disabled:opacity-50"
              >
                <Sparkles size={13} className="shrink-0 text-accent-strong" />
                <span className="truncate">{p}</span>
              </motion.button>
            ))}
          </div>
        )}
      </motion.div>
    </div>
  );
}
