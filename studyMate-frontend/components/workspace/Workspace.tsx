"use client";

import { PanelLeft, Quote } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { fetchHealth, type Health } from "@/lib/api";
import { useMediaQuery } from "@/lib/media";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { IconButton } from "../ui/Button";
import { ThemeToggle } from "../ui/ThemeToggle";
import { Toasts } from "../ui/Toasts";
import { Chat } from "./Chat";
import { Sidebar } from "./Sidebar";
import { SourcesPanel } from "./SourcesPanel";

export function Workspace() {
  const loadDocuments = useStore((s) => s.loadDocuments);
  const loadConversations = useStore((s) => s.loadConversations);
  const sidebarOpen = useStore((s) => s.sidebarOpen);
  const setSidebarOpen = useStore((s) => s.setSidebarOpen);
  const sourcesOpen = useStore((s) => s.sourcesOpen);
  const setSourcesOpen = useStore((s) => s.setSourcesOpen);
  const sourcesDrawer = useStore((s) => s.sourcesDrawer);
  const setSourcesDrawer = useStore((s) => s.setSourcesDrawer);
  const isWide = useMediaQuery("(min-width: 1280px)");
  const activeId = useStore((s) => s.activeConversationId);
  const conversations = useStore((s) => s.conversations);
  const [health, setHealth] = useState<Health | null | "offline">(null);

  useEffect(() => {
    void loadDocuments();
    void loadConversations();
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth("offline"));
  }, [loadDocuments, loadConversations]);

  // Keyboard: "/" focuses the composer, Escape closes drawers.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && !(e.target instanceof HTMLTextAreaElement) && !(e.target instanceof HTMLInputElement)) {
        e.preventDefault();
        document.getElementById("composer")?.focus();
      }
      if (e.key === "Escape") {
        setSidebarOpen(false);
        setSourcesDrawer(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setSidebarOpen, setSourcesDrawer]);

  const title = conversations.find((c) => c.id === activeId)?.title ?? "New conversation";
  const disabledReason =
    health === "offline"
      ? "The StudyMate server is offline"
      : health && !health.llm_configured
        ? "The server has no LLM API key configured"
        : null;

  return (
    <div className="flex h-dvh overflow-hidden bg-bg">
      {/* Sidebar: fixed column on large screens, drawer below. */}
      <Sidebar className="hidden w-[286px] shrink-0 border-r lg:flex" />
      <AnimatePresence>
        {sidebarOpen && (
          <>
            <motion.div
              key="scrim"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setSidebarOpen(false)}
              className="scrim fixed inset-0 z-30 lg:hidden"
            />
            <motion.div
              key="drawer"
              initial={{ x: -320 }}
              animate={{ x: 0 }}
              exit={{ x: -320 }}
              transition={{ type: "spring", stiffness: 380, damping: 36 }}
              className="fixed inset-y-0 left-0 z-40 w-[300px] max-w-[88vw] border-r bg-bg shadow-float lg:hidden"
            >
              <Sidebar className="bg-bg" />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b px-3 sm:px-4">
          <IconButton label="Open sidebar" onClick={() => setSidebarOpen(true)} className="lg:hidden">
            <PanelLeft size={18} />
          </IconButton>
          <h1 className="min-w-0 flex-1 truncate text-sm font-medium text-ink-2">{title}</h1>
          {health && health !== "offline" && (
            <span className="hidden items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[11px] text-ink-3 md:inline-flex" title="Answering model">
              <span className={cn("h-1.5 w-1.5 rounded-full", health.llm_configured ? "bg-ok" : "bg-warn")} />
              {health.llm_provider === "mock" ? "mock answers" : health.model}
            </span>
          )}
          {health === "offline" && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-danger/40 px-2.5 py-1 text-[11px] text-danger">
              <span className="h-1.5 w-1.5 rounded-full bg-danger" /> offline
            </span>
          )}
          <ThemeToggle />
          <IconButton
            label={(isWide ? sourcesOpen : sourcesDrawer) ? "Hide sources" : "Show sources"}
            onClick={() => (isWide ? setSourcesOpen(!sourcesOpen) : setSourcesDrawer(!sourcesDrawer))}
            className={cn((isWide ? sourcesOpen : sourcesDrawer) && "bg-surface-3 text-ink")}
          >
            <Quote size={17} />
          </IconButton>
        </header>
        <Chat disabledReason={disabledReason} />
      </main>

      {/* Sources: inline column on xl, drawer below. */}
      <AnimatePresence initial={false}>
        {isWide && sourcesOpen && (
          <motion.div
            key="sources-col"
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 340, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 34 }}
            className="shrink-0 overflow-hidden border-l"
          >
            <SourcesPanel className="w-[340px]" />
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {!isWide && sourcesDrawer && (
          <>
            <motion.div
              key="sources-scrim"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setSourcesDrawer(false)}
              className="scrim fixed inset-0 z-30 xl:hidden"
            />
            <motion.div
              key="sources-drawer"
              initial={{ x: 360 }}
              animate={{ x: 0 }}
              exit={{ x: 360 }}
              transition={{ type: "spring", stiffness: 380, damping: 36 }}
              className="fixed inset-y-0 right-0 z-40 w-[340px] max-w-[92vw] border-l bg-bg shadow-float xl:hidden"
            >
              <SourcesPanel className="bg-bg" />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <Toasts />
    </div>
  );
}
