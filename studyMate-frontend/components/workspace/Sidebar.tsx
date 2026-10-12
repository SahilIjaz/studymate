"use client";

import { MessageSquare, Plus, Trash2, X } from "lucide-react";
import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { useStore } from "@/lib/store";
import { cn, relativeTime } from "@/lib/utils";
import { Button, IconButton } from "../ui/Button";
import { Wordmark } from "../ui/Logo";
import { DocumentCard, UploadRow } from "./DocumentCard";
import { UploadZone } from "./UploadZone";

export function Sidebar({ className }: { className?: string }) {
  const documents = useStore((s) => s.documents);
  const uploads = useStore((s) => s.uploads);
  const documentsLoaded = useStore((s) => s.documentsLoaded);
  const conversations = useStore((s) => s.conversations);
  const active = useStore((s) => s.activeConversationId);
  const open = useStore((s) => s.openConversation);
  const remove = useStore((s) => s.deleteConversation);
  const scope = useStore((s) => s.scope);
  const clearScope = useStore((s) => s.clearScope);
  const setSidebarOpen = useStore((s) => s.setSidebarOpen);

  return (
    <aside className={cn("flex h-full flex-col bg-bg-2/70", className)}>
      <div className="flex h-14 items-center justify-between px-4">
        <Link href="/" className="rounded-lg">
          <Wordmark />
        </Link>
        <IconButton label="Close sidebar" onClick={() => setSidebarOpen(false)} className="lg:hidden">
          <X size={17} />
        </IconButton>
      </div>

      <div className="px-3">
        <Button variant="secondary" className="w-full justify-start" onClick={() => open(null)}>
          <Plus size={16} /> New conversation
        </Button>
      </div>

      <div className="mt-4 flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-3 pb-4">
        <section>
          <header className="mb-2 flex items-center justify-between px-1">
            <h2 className="eyebrow">Documents</h2>
            {scope.length > 0 && (
              <button type="button" onClick={clearScope} className="text-[11.5px] text-ink-3 underline-offset-2 hover:underline">
                Clear scope
              </button>
            )}
          </header>
          <UploadZone compact />
          <div className="mt-2 flex flex-col gap-0.5">
            <AnimatePresence initial={false}>
              {uploads.map((u) => (
                <UploadRow key={u.id} upload={u} />
              ))}
              {documents.map((d) => (
                <DocumentCard key={d.id} doc={d} />
              ))}
            </AnimatePresence>
            {documentsLoaded && documents.length === 0 && uploads.length === 0 && (
              <p className="px-2 pt-2 text-[12.5px] leading-snug text-ink-3">
                Nothing here yet. Your PDFs stay in this browser&apos;s workspace.
              </p>
            )}
          </div>
        </section>

        <section>
          <h2 className="eyebrow mb-2 px-1">Conversations</h2>
          <div className="flex flex-col gap-0.5">
            <AnimatePresence initial={false}>
              {conversations.map((c) => (
                <motion.div
                  key={c.id}
                  layout
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, x: -12, transition: { duration: 0.15 } }}
                  className={cn(
                    "group relative flex items-center gap-2 rounded-xl pr-8 transition-colors",
                    c.id === active ? "bg-surface shadow-card ring-1 ring-border" : "hover:bg-surface-2",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => open(c.id)}
                    aria-current={c.id === active ? "true" : undefined}
                    className="flex min-w-0 flex-1 items-center gap-2.5 px-2.5 py-2 text-left"
                  >
                    <MessageSquare size={14} className="shrink-0 text-ink-3" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium leading-snug">{c.title}</span>
                      <span className="block text-[11px] text-ink-3">{relativeTime(c.updated_at)}</span>
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(c.id)}
                    aria-label={`Delete conversation ${c.title}`}
                    className="absolute right-1.5 rounded-md p-1 text-ink-4 opacity-0 transition hover:bg-surface-3 hover:text-danger focus-visible:opacity-100 group-hover:opacity-100"
                  >
                    <Trash2 size={13} />
                  </button>
                </motion.div>
              ))}
            </AnimatePresence>
            {conversations.length === 0 && (
              <p className="px-2 text-[12.5px] leading-snug text-ink-3">Your questions will be saved here.</p>
            )}
          </div>
        </section>
      </div>
    </aside>
  );
}
