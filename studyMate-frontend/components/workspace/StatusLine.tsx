"use client";

import { AnimatePresence, motion } from "motion/react";
import type { Stage } from "@/lib/store";

const copy: Record<Exclude<Stage, null>, string> = {
  retrieving: "Searching your documents",
  thinking: "Reading the passages",
  answering: "Writing",
};

export function StatusLine({ stage, sourceCount }: { stage: Stage; sourceCount: number }) {
  if (!stage) return null;
  const text = stage === "thinking" && sourceCount ? `Reading ${sourceCount} passage${sourceCount === 1 ? "" : "s"}` : copy[stage];
  return (
    <div className="flex h-6 items-center gap-2 text-[13px] text-ink-3" aria-live="polite">
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-accent-strong" />
      </span>
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={text}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.18 }}
        >
          {text}
          <span className="inline-block w-4 text-left after:animate-[blink_1.2s_steps(4,end)_infinite] after:content-['…']" />
        </motion.span>
      </AnimatePresence>
    </div>
  );
}
