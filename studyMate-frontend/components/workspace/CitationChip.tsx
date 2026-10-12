"use client";

import { motion } from "motion/react";
import type { Citation } from "@/lib/api";
import { cn, pageLabel } from "@/lib/utils";

export function CitationChip({
  n,
  citation,
  active,
  onSelect,
}: {
  n: number;
  citation?: Citation;
  active?: boolean;
  onSelect?: (n: number) => void;
}) {
  const label = citation ? `${citation.filename}, ${pageLabel(citation.page_start, citation.page_end)}` : `Source ${n}`;
  return (
    <motion.button
      type="button"
      initial={{ scale: 0.6, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 500, damping: 26 }}
      onClick={() => onSelect?.(n)}
      title={label}
      aria-label={`Source ${n}: ${label}`}
      className={cn(
        "mx-0.5 inline-flex h-[1.25em] min-w-[1.5em] -translate-y-[0.1em] items-center justify-center rounded-[5px] px-1 align-middle font-mono text-[0.68em] font-medium leading-none transition-colors",
        "bg-mark text-mark-ink ring-1 ring-inset ring-accent/40 hover:bg-accent hover:text-accent-ink",
        active && "bg-accent text-accent-ink ring-accent-strong",
      )}
    >
      {n}
    </motion.button>
  );
}
