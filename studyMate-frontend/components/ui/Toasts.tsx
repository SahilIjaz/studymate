"use client";

import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";

const icons = {
  info: <Info size={16} className="text-ink-2" />,
  success: <CheckCircle2 size={16} className="text-ok" />,
  error: <AlertTriangle size={16} className="text-danger" />,
};

export function Toasts() {
  const toasts = useStore((s) => s.toasts);
  const dismiss = useStore((s) => s.dismissToast);
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex flex-col items-center gap-2 px-4 pb-[max(1rem,env(safe-area-inset-bottom))] sm:items-end sm:px-6">
      <AnimatePresence initial={false}>
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            layout
            initial={{ opacity: 0, y: 16, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.96 }}
            transition={{ type: "spring", stiffness: 420, damping: 32 }}
            role={t.kind === "error" ? "alert" : "status"}
            className={cn(
              "paper pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-2xl px-4 py-3",
              t.kind === "error" && "border-danger/40",
            )}
          >
            <span className="mt-0.5">{icons[t.kind]}</span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium leading-snug">{t.title}</p>
              {t.body && <p className="mt-0.5 text-[13px] leading-snug text-ink-3">{t.body}</p>}
            </div>
            <button
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss"
              className="-mr-1 -mt-0.5 rounded-lg p-1 text-ink-3 hover:bg-surface-3 hover:text-ink"
            >
              <X size={14} />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
