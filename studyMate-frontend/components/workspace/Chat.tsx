"use client";

import { ArrowDown } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { useStore } from "@/lib/store";
import { Composer } from "./Composer";
import { EmptyState } from "./EmptyState";
import { MessageBubble } from "./MessageBubble";

export function Chat({ disabledReason }: { disabledReason?: string | null }) {
  const messages = useStore((s) => s.messages);
  const stage = useStore((s) => s.stage);
  const streaming = useStore((s) => s.streaming);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);

  // Follow the stream while the reader is at the bottom; stop when they scroll up.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  const lastContent = messages[messages.length - 1]?.content;
  useEffect(() => {
    if (pinned) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages.length, lastContent, pinned, stage]);

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="flex min-h-full flex-col">
            <EmptyState />
          </div>
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col gap-7 px-4 pb-6 pt-6 sm:px-6">
            {messages.map((m, i) => (
              <MessageBubble key={m.id} message={m} isLast={i === messages.length - 1} stage={stage} />
            ))}
          </div>
        )}
      </div>

      <AnimatePresence>
        {!pinned && messages.length > 0 && (
          <motion.button
            type="button"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            onClick={() => {
              setPinned(true);
              scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
            }}
            className="paper absolute bottom-[7.5rem] left-1/2 z-10 flex h-9 -translate-x-1/2 items-center gap-1.5 rounded-full px-3 text-[13px] text-ink-2 hover:text-ink"
          >
            <ArrowDown size={14} /> {streaming ? "Follow answer" : "Latest"}
          </motion.button>
        )}
      </AnimatePresence>

      <Composer disabledReason={disabledReason} />
    </div>
  );
}
