import { readSSE } from "./sse";

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export type DocumentStatus = "processing" | "ready" | "failed";

export type Doc = {
  id: string;
  filename: string;
  size_bytes: number;
  page_count: number;
  chunk_count: number;
  status: DocumentStatus;
  error: string | null;
  created_at: number;
};

export type Citation = {
  n: number;
  chunk_id: number;
  document_id: string;
  filename: string;
  page_start: number;
  page_end: number;
  score: number;
  text: string;
};

export type Usage = {
  input_tokens?: number;
  output_tokens?: number;
  cache_read_input_tokens?: number;
  cache_creation_input_tokens?: number;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  usage?: Usage | null;
  status: string;
  created_at: number;
};

export type Conversation = { id: string; title: string; created_at: number; updated_at: number };

export type Health = {
  status: string;
  version: string;
  llm_provider: string;
  model: string;
  embedding_provider: string;
  llm_configured: boolean;
};

export class ApiError extends Error {
  code: string;
  status: number;
  retryAfter?: number;
  requestId?: string;

  constructor(message: string, code: string, status: number, extra: { retryAfter?: number; requestId?: string } = {}) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.retryAfter = extra.retryAfter;
    this.requestId = extra.requestId;
  }

  static offline(): ApiError {
    return new ApiError("Can't reach the StudyMate server. Is it running?", "offline", 0);
  }
}

type Handlers = {
  onMeta?: (meta: { conversation_id: string; user_message_id: string }) => void;
  onStatus?: (stage: string) => void;
  onSources?: (sources: Citation[], retrievalQuery: string) => void;
  onDelta?: (text: string) => void;
  onDone?: (done: { message_id: string; conversation_id: string; usage: Usage | null; model: string | null }) => void;
  onError?: (error: ApiError) => void;
};

export function createApi(getWorkspaceId: () => string) {
  const headers = (extra: Record<string, string> = {}): Record<string, string> => ({
    "X-Workspace-Id": getWorkspaceId(),
    ...extra,
  });

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`${API_BASE}${path}`, { ...init, headers: headers(init.headers as Record<string, string>) });
    } catch {
      throw ApiError.offline();
    }
    if (!response.ok) throw await toApiError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  return {
    health: () => fetchHealth(),

    listDocuments: () => request<{ documents: Doc[]; limit: number }>("/documents"),
    getDocument: (id: string) => request<Doc>(`/documents/${id}`),
    deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),
    suggestions: (id: string) => request<{ questions: string[] }>(`/documents/${id}/suggestions`),

    /** XMLHttpRequest so upload progress is observable. */
    uploadDocument(file: File, onProgress?: (fraction: number) => void): Promise<{ document: Doc; already_indexed: boolean }> {
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", `${API_BASE}/documents`);
        xhr.setRequestHeader("X-Workspace-Id", getWorkspaceId());
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable && onProgress) onProgress(event.loaded / event.total);
        };
        xhr.onerror = () => reject(ApiError.offline());
        xhr.onload = () => {
          let body: unknown = null;
          try {
            body = JSON.parse(xhr.responseText);
          } catch {
            /* non-JSON error page */
          }
          if (xhr.status >= 200 && xhr.status < 300) resolve(body as { document: Doc; already_indexed: boolean });
          else reject(parseErrorBody(body, xhr.status, xhr.getResponseHeader("Retry-After")));
        };
        const form = new FormData();
        form.append("file", file, file.name);
        xhr.send(form);
      });
    },

    listConversations: () => request<{ conversations: Conversation[] }>("/conversations"),
    getConversation: (id: string) => request<Conversation & { messages: Message[] }>(`/conversations/${id}`),
    deleteConversation: (id: string) => request<void>(`/conversations/${id}`, { method: "DELETE" }),

    async ask(
      body: { question: string; conversation_id?: string | null; document_ids?: string[] | null },
      handlers: Handlers,
      signal?: AbortSignal,
    ): Promise<void> {
      let response: Response;
      try {
        response = await fetch(`${API_BASE}/chat/stream`, {
          method: "POST",
          headers: headers({ "Content-Type": "application/json", Accept: "text/event-stream" }),
          body: JSON.stringify(body),
          signal,
        });
      } catch (error) {
        if ((error as Error).name === "AbortError") return;
        throw ApiError.offline();
      }
      if (!response.ok || !response.body) throw await toApiError(response);

      await readSSE(
        response.body,
        (frame) => {
          let payload: Record<string, unknown> = {};
          try {
            payload = JSON.parse(frame.data);
          } catch {
            return;
          }
          switch (frame.event) {
            case "meta":
              handlers.onMeta?.(payload as { conversation_id: string; user_message_id: string });
              break;
            case "status":
              handlers.onStatus?.(String(payload.stage));
              break;
            case "sources":
              handlers.onSources?.((payload.sources as Citation[]) ?? [], String(payload.retrieval_query ?? ""));
              break;
            case "delta":
              handlers.onDelta?.(String(payload.text ?? ""));
              break;
            case "done":
              handlers.onDone?.(payload as Parameters<NonNullable<Handlers["onDone"]>>[0]);
              break;
            case "error":
              handlers.onError?.(new ApiError(String(payload.message), String(payload.code), Number(payload.status ?? 502)));
              break;
          }
        },
        signal,
      );
    },
  };
}

export type Api = ReturnType<typeof createApi>;

export async function fetchHealth(): Promise<Health> {
  try {
    const response = await fetch(`${API_BASE}/health`, { cache: "no-store" });
    if (!response.ok) throw await toApiError(response);
    return (await response.json()) as Health;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw ApiError.offline();
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    /* ignore */
  }
  return parseErrorBody(body, response.status, response.headers.get("Retry-After"));
}

function parseErrorBody(body: unknown, status: number, retryAfterHeader: string | null): ApiError {
  const err = (body as { error?: { code?: string; message?: string; request_id?: string } } | null)?.error;
  const retryAfter = retryAfterHeader ? parseInt(retryAfterHeader, 10) : undefined;
  return new ApiError(
    err?.message ?? (status === 0 ? "Network error." : `Request failed (${status}).`),
    err?.code ?? "http_error",
    status,
    { retryAfter: Number.isFinite(retryAfter) ? retryAfter : undefined, requestId: err?.request_id },
  );
}
