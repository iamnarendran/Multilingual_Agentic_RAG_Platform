"use client";

import { FileUp, LibraryBig, Menu } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Spinner } from "@/components/brand";
import { Composer } from "@/components/composer";
import { EmptyState } from "@/components/empty-state";
import { AssistantMessage, UserMessage } from "@/components/message";
import { api, ApiError } from "@/lib/api";
import { streamChat } from "@/lib/stream";
import type { ChatMessage, ConversationDetail, ConversationInfo, DocumentInfo, Source, Step, StoredMessage, Validation } from "@/lib/types";

type Props = {
  conversationId: string | null;
  conversations: ConversationInfo[] | undefined;
  documents: DocumentInfo[];
  scope: string[];
  llmConfigured: boolean;
  onOpenSidebar: () => void;
  onOpenLibrary: () => void;
  onUpload: (files: File[]) => void;
  onConversationsChanged: () => void;
};

const blank = (role: ChatMessage["role"], content = ""): ChatMessage => ({
  id: `local-${crypto.randomUUID()}`,
  role,
  content,
  status: role === "assistant" ? "streaming" : "complete",
  steps: [],
  sources: [],
  validation: null,
  language: null,
  queryType: null,
  error: null,
  latencyMs: null,
});

function fromStored(m: StoredMessage): ChatMessage {
  return {
    id: m.id,
    role: m.role,
    content: m.content,
    status: m.status,
    steps: m.trace ?? [],
    sources: m.sources ?? [],
    validation: m.validation,
    language: m.language,
    queryType: m.query_type,
    error: m.status === "error" && !m.content ? "This answer could not be completed." : null,
    latencyMs: m.usage?.latency_ms ?? null,
  };
}

export function ChatView(props: Props) {
  const { conversationId, conversations, documents, scope, llmConfigured, onOpenSidebar, onOpenLibrary, onUpload, onConversationsChanged } =
    props;
  const router = useRouter();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const shownConversation = useRef<string | null | undefined>(undefined);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  // Load a conversation when the URL points somewhere we aren't already showing.
  useEffect(() => {
    if (conversationId === shownConversation.current) return;
    abortRef.current?.abort();
    shownConversation.current = conversationId;
    setLoadError(null);
    stickToBottom.current = true;
    if (!conversationId) {
      setMessages([]);
      return;
    }
    setLoading(true);
    setMessages([]);
    api<ConversationDetail>(`/api/conversations/${conversationId}`)
      .then((detail) => {
        if (shownConversation.current === conversationId) setMessages(detail.messages.map(fromStored));
      })
      .catch((err: ApiError) => {
        if (shownConversation.current === conversationId) {
          setLoadError(err.status === 404 ? "This conversation doesn't exist or was deleted." : err.message);
        }
      })
      .finally(() => setLoading(false));
  }, [conversationId]);

  // Keep the newest content in view unless the reader scrolled up.
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const send = useCallback(
    async (text: string) => {
      if (streaming) return;
      const userMsg = blank("user", text);
      const reply = blank("assistant");
      stickToBottom.current = true;
      setMessages((ms) => [...ms, userMsg, reply]);
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;
      const patch = (id: string, fn: (m: ChatMessage) => ChatMessage) =>
        setMessages((ms) => ms.map((m) => (m.id === id ? fn(m) : m)));

      // Batch tokens into one render per animation frame.
      let userId = userMsg.id;
      let replyId = reply.id;
      let pending = "";
      let frame = 0;
      const flush = () => {
        frame = 0;
        if (!pending) return;
        const chunk = pending;
        pending = "";
        patch(replyId, (m) => ({ ...m, content: m.content + chunk }));
      };

      try {
        for await (const { event, data } of streamChat(
          { message: text, conversation_id: shownConversation.current ?? null, document_ids: scope.length ? scope : null },
          controller.signal,
        )) {
          switch (event) {
            case "start": {
              const id = data.conversation_id as string;
              const serverUserId = data.user_message_id as string;
              patch(userId, (m) => ({ ...m, id: serverUserId }));
              userId = serverUserId;
              if (data.created) {
                shownConversation.current = id;
                router.replace(`/c/${id}`, { scroll: false });
                onConversationsChanged();
              }
              break;
            }
            case "meta":
              if (data.language) {
                const language = data.language as string;
                patch(userId, (m) => ({ ...m, language }));
                patch(replyId, (m) => ({ ...m, language }));
              }
              if (data.query_type) patch(replyId, (m) => ({ ...m, queryType: data.query_type as string }));
              break;
            case "step": {
              const step = data as unknown as Step;
              patch(replyId, (m) => {
                if (step.status === "running") return { ...m, steps: [...m.steps, step] };
                const idx = m.steps.findLastIndex((s) => s.agent === step.agent && s.status === "running");
                const steps = idx === -1 ? [...m.steps, step] : m.steps.map((s, i) => (i === idx ? step : s));
                return { ...m, steps };
              });
              break;
            }
            case "sources":
              patch(replyId, (m) => ({ ...m, sources: data.sources as Source[] }));
              break;
            case "token":
              pending += data.text as string;
              if (!frame) frame = requestAnimationFrame(flush);
              break;
            case "validation":
              flush();
              patch(replyId, (m) => ({ ...m, validation: data.validation as Validation }));
              break;
            case "error":
              flush();
              patch(replyId, (m) => ({ ...m, error: data.message as string }));
              break;
            case "done": {
              flush();
              const finalId = (data.message_id as string) || replyId;
              patch(replyId, (m) => ({
                ...m,
                id: finalId,
                status: data.status as ChatMessage["status"],
                latencyMs: (data.latency_ms as number) ?? null,
              }));
              replyId = finalId;
              break;
            }
          }
        }
      } catch (err) {
        if (frame) cancelAnimationFrame(frame);
        flush();
        if ((err as Error).name === "AbortError") {
          patch(replyId, (m) => ({ ...m, status: "stopped" }));
        } else {
          patch(replyId, (m) => ({ ...m, status: "error", error: (err as Error).message }));
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        setMessages((ms) => ms.map((m) => (m.id === replyId && m.status === "streaming" ? { ...m, status: "complete" } : m)));
        setStreaming(false);
        onConversationsChanged();
      }
    },
    [streaming, scope, router, onConversationsChanged],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const title = conversationId ? conversations?.find((c) => c.id === conversationId)?.title ?? "" : "New chat";
  const readyDocs = documents.filter((d) => d.status === "ready");
  const scopeLabel = scope.length
    ? `Searching ${scope.length} of ${readyDocs.length} documents`
    : readyDocs.length
      ? `Searching all ${readyDocs.length} document${readyDocs.length === 1 ? "" : "s"}`
      : "No documents yet";

  return (
    <div
      className="relative flex h-full flex-col"
      onDragEnter={(e) => {
        if (e.dataTransfer.types.includes("Files")) setDragging(true);
      }}
      onDragOver={(e) => e.dataTransfer.types.includes("Files") && e.preventDefault()}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        onUpload(Array.from(e.dataTransfer.files));
      }}
    >
      <header className="flex h-14 shrink-0 items-center gap-2 border-b border-line px-3 sm:px-5">
        <button className="rounded-lg p-1.5 text-ink-soft hover:bg-wash lg:hidden" onClick={onOpenSidebar} aria-label="Open menu">
          <Menu className="size-5" />
        </button>
        <h1 className="min-w-0 flex-1 truncate font-semibold" style={{ fontStretch: "95%" }}>
          {title}
        </h1>
        <button
          onClick={onOpenLibrary}
          className="flex items-center gap-2 rounded-[10px] border border-line px-2.5 py-1.5 text-sm text-ink-soft transition-colors hover:border-indigo/40 hover:text-ink"
        >
          <LibraryBig className="size-4 text-indigo" />
          <span className="hidden sm:inline">{scopeLabel}</span>
          <span className="sm:hidden">Library</span>
        </button>
      </header>

      {!llmConfigured && (
        <div role="status" className="border-b border-line bg-amber-wash px-5 py-2.5 text-sm text-amber">
          The server has no language model configured, so questions can&apos;t be answered yet. Set LLM_API_KEY in the
          backend&apos;s .env file and restart it.
        </div>
      )}

      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        className="scroll-area flex-1 overflow-y-auto"
      >
        {loading ? (
          <div className="flex justify-center py-16 text-ink-faint">
            <Spinner className="size-6" />
          </div>
        ) : loadError ? (
          <p className="mx-auto max-w-3xl px-5 py-16 text-ink-soft">{loadError}</p>
        ) : messages.length === 0 ? (
          <EmptyState documents={documents} onUpload={onUpload} onAsk={send} onOpenLibrary={onOpenLibrary} />
        ) : (
          <div className="mx-auto max-w-3xl space-y-8 px-4 pb-10 pt-8 sm:px-6">
            {messages.map((m) =>
              m.role === "user" ? <UserMessage key={m.id} message={m} /> : <AssistantMessage key={m.id} message={m} />,
            )}
          </div>
        )}
      </div>

      <Composer streaming={streaming} onSend={send} onStop={stop} onUpload={onUpload} disabled={!!loadError} />

      {dragging && (
        <div className="pointer-events-none absolute inset-3 z-20 flex flex-col items-center justify-center gap-3 rounded-[18px] border-2 border-dashed border-indigo bg-paper/90 text-indigo">
          <FileUp className="size-8" />
          <p className="text-lg font-semibold">Drop files to add them to your library</p>
        </div>
      )}
    </div>
  );
}
