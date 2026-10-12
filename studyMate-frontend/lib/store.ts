"use client";

import { create } from "zustand";
import { ApiError, createApi, type Citation, type Conversation, type Doc, type Message, type Usage } from "./api";
import { uuid } from "./utils";

export type UploadState = { id: string; filename: string; size: number; progress: number; error?: string };

export type Toast = { id: string; kind: "info" | "success" | "error"; title: string; body?: string };

export type Stage = "retrieving" | "thinking" | "answering" | null;

type Store = {
  workspaceId: string;
  documents: Doc[];
  uploads: UploadState[];
  suggestions: Record<string, string[]>;
  scope: string[];
  documentsLoaded: boolean;
  loadDocuments: () => Promise<void>;
  upload: (files: File[]) => Promise<void>;
  deleteDocument: (id: string) => Promise<void>;
  toggleScope: (id: string) => void;
  clearScope: () => void;

  conversations: Conversation[];
  activeConversationId: string | null;
  messages: Message[];
  loadConversations: () => Promise<void>;
  openConversation: (id: string | null) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;

  streaming: boolean;
  stage: Stage;
  retrievalQuery: string | null;
  ask: (question: string) => Promise<void>;
  stop: () => void;

  selectedCitation: { messageId: string; n: number } | null;
  selectCitation: (selection: { messageId: string; n: number } | null) => void;
  sourcesOpen: boolean; // desktop column
  setSourcesOpen: (open: boolean) => void;
  sourcesDrawer: boolean; // phone/tablet overlay
  setSourcesDrawer: (open: boolean) => void;
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;

  toasts: Toast[];
  toast: (toast: Omit<Toast, "id">) => void;
  dismissToast: (id: string) => void;

  draft: string;
  setDraft: (draft: string) => void;
};

const WORKSPACE_KEY = "studymate:workspace";
const CONVERSATION_KEY = "studymate:conversation";

function readStorage(key: string): string | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string | null) {
  try {
    if (typeof window === "undefined") return;
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* private mode */
  }
}

function initialWorkspace(): string {
  const existing = readStorage(WORKSPACE_KEY);
  if (existing && /^[0-9a-f-]{36}$/i.test(existing)) return existing;
  const fresh = uuid();
  writeStorage(WORKSPACE_KEY, fresh);
  return fresh;
}

let controller: AbortController | null = null;
const pollers = new Map<string, number>();

export const useStore = create<Store>((set, get) => {
  const api = createApi(() => get().workspaceId);

  const toast = (t: Omit<Toast, "id">) => {
    const id = uuid();
    set((s) => ({ toasts: [...s.toasts, { ...t, id }] }));
    window.setTimeout(() => get().dismissToast(id), t.kind === "error" ? 7000 : 4000);
  };

  const describe = (error: unknown): string => (error instanceof ApiError ? error.message : "Something went wrong.");

  const pollDocument = (id: string) => {
    if (pollers.has(id)) return;
    const tick = async () => {
      try {
        const doc = await api.getDocument(id);
        set((s) => ({ documents: s.documents.map((d) => (d.id === id ? doc : d)) }));
        if (doc.status === "processing") {
          pollers.set(id, window.setTimeout(tick, 1200));
          return;
        }
        pollers.delete(id);
        if (doc.status === "ready") {
          toast({ kind: "success", title: `${doc.filename} is ready`, body: `${doc.page_count} pages, ${doc.chunk_count} passages indexed.` });
          api
            .suggestions(id)
            .then(({ questions }) => set((s) => ({ suggestions: { ...s.suggestions, [id]: questions } })))
            .catch(() => undefined);
        } else {
          toast({ kind: "error", title: `Couldn't index ${doc.filename}`, body: doc.error ?? undefined });
        }
      } catch (error) {
        pollers.delete(id);
        toast({ kind: "error", title: "Lost track of an upload", body: describe(error) });
      }
    };
    pollers.set(id, window.setTimeout(tick, 800));
  };

  return {
    workspaceId: initialWorkspace(),
    documents: [],
    uploads: [],
    suggestions: {},
    scope: [],
    documentsLoaded: false,

    loadDocuments: async () => {
      try {
        const { documents } = await api.listDocuments();
        set({ documents, documentsLoaded: true });
        documents.filter((d) => d.status === "processing").forEach((d) => pollDocument(d.id));
      } catch (error) {
        set({ documentsLoaded: true });
        toast({ kind: "error", title: "Couldn't load documents", body: describe(error) });
      }
    },

    upload: async (files) => {
      for (const file of files) {
        const uploadId = uuid();
        set((s) => ({ uploads: [...s.uploads, { id: uploadId, filename: file.name, size: file.size, progress: 0 }] }));
        try {
          const { document, already_indexed } = await api.uploadDocument(file, (fraction) =>
            set((s) => ({ uploads: s.uploads.map((u) => (u.id === uploadId ? { ...u, progress: fraction } : u)) })),
          );
          set((s) => ({
            uploads: s.uploads.filter((u) => u.id !== uploadId),
            documents: s.documents.some((d) => d.id === document.id) ? s.documents : [document, ...s.documents],
          }));
          if (already_indexed) toast({ kind: "info", title: "Already in your workspace", body: `${document.filename} was uploaded before.` });
          else pollDocument(document.id);
        } catch (error) {
          const message = describe(error);
          set((s) => ({ uploads: s.uploads.map((u) => (u.id === uploadId ? { ...u, error: message } : u)) }));
          toast({ kind: "error", title: `Couldn't upload ${file.name}`, body: message });
          window.setTimeout(() => set((s) => ({ uploads: s.uploads.filter((u) => u.id !== uploadId) })), 6000);
        }
      }
    },

    deleteDocument: async (id) => {
      const previous = get().documents;
      set((s) => ({ documents: s.documents.filter((d) => d.id !== id), scope: s.scope.filter((x) => x !== id) }));
      try {
        await api.deleteDocument(id);
      } catch (error) {
        set({ documents: previous });
        toast({ kind: "error", title: "Couldn't delete that document", body: describe(error) });
      }
    },

    toggleScope: (id) =>
      set((s) => ({ scope: s.scope.includes(id) ? s.scope.filter((x) => x !== id) : [...s.scope, id] })),
    clearScope: () => set({ scope: [] }),

    conversations: [],
    activeConversationId: null,
    messages: [],

    loadConversations: async () => {
      try {
        const { conversations } = await api.listConversations();
        set({ conversations });
        const remembered = readStorage(CONVERSATION_KEY);
        if (remembered && conversations.some((c) => c.id === remembered) && !get().activeConversationId) {
          await get().openConversation(remembered);
        }
      } catch (error) {
        toast({ kind: "error", title: "Couldn't load conversations", body: describe(error) });
      }
    },

    openConversation: async (id) => {
      get().stop();
      writeStorage(CONVERSATION_KEY, id);
      if (!id) {
        set({ activeConversationId: null, messages: [], selectedCitation: null, sidebarOpen: false });
        return;
      }
      set({ activeConversationId: id, selectedCitation: null, sidebarOpen: false });
      try {
        const detail = await api.getConversation(id);
        if (get().activeConversationId === id) set({ messages: detail.messages });
      } catch (error) {
        toast({ kind: "error", title: "Couldn't open that conversation", body: describe(error) });
        set({ activeConversationId: null, messages: [] });
      }
    },

    deleteConversation: async (id) => {
      const previous = get().conversations;
      set((s) => ({ conversations: s.conversations.filter((c) => c.id !== id) }));
      if (get().activeConversationId === id) await get().openConversation(null);
      try {
        await api.deleteConversation(id);
      } catch (error) {
        set({ conversations: previous });
        toast({ kind: "error", title: "Couldn't delete that conversation", body: describe(error) });
      }
    },

    streaming: false,
    stage: null,
    retrievalQuery: null,

    ask: async (question) => {
      const trimmed = question.trim();
      if (!trimmed || get().streaming) return;

      const userId = `local_${uuid()}`;
      const assistantId = `local_${uuid()}`;
      const now = Date.now() / 1000;
      set((s) => ({
        draft: "",
        streaming: true,
        stage: "retrieving",
        retrievalQuery: null,
        selectedCitation: null,
        messages: [
          ...s.messages,
          { id: userId, role: "user", content: trimmed, citations: [], status: "complete", created_at: now },
          { id: assistantId, role: "assistant", content: "", citations: [], status: "streaming", created_at: now },
        ],
      }));

      controller = new AbortController();
      const patch = (id: string, fn: (m: Message) => Message) =>
        set((s) => ({ messages: s.messages.map((m) => (m.id === id ? fn(m) : m)) }));

      // Deltas are batched per animation frame so Markdown re-renders stay cheap.
      let pending = "";
      let frame: number | null = null;
      const flush = () => {
        frame = null;
        if (!pending) return;
        const text = pending;
        pending = "";
        patch(assistantId, (m) => ({ ...m, content: m.content + text }));
      };

      try {
        await api.ask(
          { question: trimmed, conversation_id: get().activeConversationId, document_ids: get().scope.length ? get().scope : null },
          {
            onMeta: ({ conversation_id, user_message_id }) => {
              patch(userId, (m) => ({ ...m, id: user_message_id }));
              if (get().activeConversationId !== conversation_id) {
                set({ activeConversationId: conversation_id });
                writeStorage(CONVERSATION_KEY, conversation_id);
                const title = trimmed.length > 60 ? `${trimmed.slice(0, 57).trimEnd()}...` : trimmed;
                set((s) => ({
                  conversations: [{ id: conversation_id, title, created_at: now, updated_at: now }, ...s.conversations],
                }));
              } else {
                set((s) => ({
                  conversations: s.conversations
                    .map((c) => (c.id === conversation_id ? { ...c, updated_at: now } : c))
                    .sort((a, b) => b.updated_at - a.updated_at),
                }));
              }
            },
            onStatus: (stage) => set({ stage: stage as Stage }),
            onSources: (sources, retrievalQuery) => {
              set({ retrievalQuery });
              patch(assistantId, (m) => ({ ...m, citations: sources }));
            },
            onDelta: (text) => {
              if (get().stage !== "answering") set({ stage: "answering" });
              pending += text;
              if (frame === null) frame = window.requestAnimationFrame(flush);
            },
            onDone: ({ message_id, usage }) => {
              if (frame !== null) window.cancelAnimationFrame(frame);
              flush();
              patch(assistantId, (m) => ({ ...m, id: message_id, status: "complete", usage: usage as Usage | null }));
            },
            onError: (error) => {
              if (frame !== null) window.cancelAnimationFrame(frame);
              flush();
              patch(assistantId, (m) => ({ ...m, status: "failed", content: m.content || error.message }));
              toast({ kind: "error", title: "Couldn't answer that", body: error.message });
            },
          },
          controller.signal,
        );
      } catch (error) {
        flush();
        const message = describe(error);
        patch(assistantId, (m) => ({ ...m, status: "failed", content: m.content || message }));
        toast({ kind: "error", title: "Couldn't answer that", body: message });
      } finally {
        if (frame !== null) window.cancelAnimationFrame(frame);
        flush();
        controller = null;
        set({ streaming: false, stage: null });
        set((s) => ({
          messages: s.messages.map((m) => (m.id === assistantId && m.status === "streaming" ? { ...m, status: "interrupted" } : m)),
        }));
      }
    },

    stop: () => {
      controller?.abort();
      controller = null;
    },

    selectedCitation: null,
    selectCitation: (selection) =>
      set({
        selectedCitation: selection,
        sourcesOpen: selection !== null ? true : get().sourcesOpen,
        // The overlay drawer only matters below the xl breakpoint.
        sourcesDrawer: selection !== null && !window.matchMedia("(min-width: 1280px)").matches ? true : get().sourcesDrawer,
      }),
    sourcesOpen: true,
    setSourcesOpen: (open) => set({ sourcesOpen: open }),
    sourcesDrawer: false,
    setSourcesDrawer: (open) => set({ sourcesDrawer: open }),
    sidebarOpen: false,
    setSidebarOpen: (open) => set({ sidebarOpen: open }),

    toasts: [],
    toast,
    dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

    draft: "",
    setDraft: (draft) => set({ draft }),
  };
});

export function citationFor(messages: Message[], selection: { messageId: string; n: number } | null): Citation | null {
  if (!selection) return null;
  const message = messages.find((m) => m.id === selection.messageId);
  return message?.citations.find((c) => c.n === selection.n) ?? null;
}
