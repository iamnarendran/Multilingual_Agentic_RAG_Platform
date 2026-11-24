"use client";

import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import useSWR from "swr";
import { Spinner } from "@/components/brand";
import { ChatView } from "@/components/chat-view";
import { LibraryPanel } from "@/components/library";
import { Sidebar } from "@/components/sidebar";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ConversationInfo, DocumentInfo, Health, User } from "@/lib/types";

export function Workspace() {
  const { user, ready } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (ready && !user) router.replace("/login");
  }, [ready, user, router]);

  if (!ready || !user) {
    return (
      <div className="flex h-dvh items-center justify-center text-ink-faint">
        <Spinner className="size-6" />
      </div>
    );
  }
  return <WorkspaceInner user={user} />;
}

const keyFetcher = <T,>([path]: [string, string]) => api<T>(path);

function WorkspaceInner({ user }: { user: User }) {
  const pathname = usePathname();
  const conversationId = pathname.startsWith("/c/") ? decodeURIComponent(pathname.slice(3)) : null;

  const conversations = useSWR<ConversationInfo[]>(["/api/conversations", user.id], keyFetcher);
  const documents = useSWR<DocumentInfo[]>(["/api/documents", user.id], keyFetcher, {
    refreshInterval: (docs) => (docs?.some((d) => d.status === "processing") ? 2000 : 0),
  });
  const health = useSWR<Health>("/api/health", (p: string) => api<Health>(p), { revalidateOnFocus: false });

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [scope, setScope] = useState<string[]>([]);
  const [uploadErrors, setUploadErrors] = useState<string[]>([]);

  const docs = documents.data ?? [];
  const readyIds = docs.filter((d) => d.status === "ready").map((d) => d.id);
  const activeScope = scope.filter((id) => readyIds.includes(id));

  const upload = useCallback(
    async (files: File[]) => {
      if (!files.length) return;
      setLibraryOpen(true);
      setUploadErrors([]);
      const limits = health.data?.limits;
      for (const file of files) {
        const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
        if (limits && !limits.extensions.includes(ext)) {
          setUploadErrors((e) => [...e, `${file.name}: only ${limits.extensions.join(", ")} files can be added.`]);
          continue;
        }
        if (limits && file.size > limits.max_upload_mb * 1024 * 1024) {
          setUploadErrors((e) => [...e, `${file.name}: larger than ${limits.max_upload_mb} MB.`]);
          continue;
        }
        const form = new FormData();
        form.append("file", file);
        try {
          await api<DocumentInfo>("/api/documents", { method: "POST", body: form });
        } catch (err) {
          setUploadErrors((e) => [...e, `${file.name}: ${(err as Error).message}`]);
        }
        await documents.mutate();
      }
    },
    [documents, health.data],
  );

  return (
    <div className="flex h-dvh overflow-hidden">
      <Sidebar
        user={user}
        conversations={conversations.data}
        activeId={conversationId}
        documents={docs}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onOpenLibrary={() => setLibraryOpen(true)}
        onChanged={() => conversations.mutate()}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        <ChatView
          conversationId={conversationId}
          conversations={conversations.data}
          documents={docs}
          scope={activeScope}
          llmConfigured={health.data?.llm.configured ?? true}
          onOpenSidebar={() => setSidebarOpen(true)}
          onOpenLibrary={() => setLibraryOpen(true)}
          onUpload={upload}
          onConversationsChanged={() => conversations.mutate()}
        />
      </main>
      <LibraryPanel
        open={libraryOpen}
        onClose={() => setLibraryOpen(false)}
        documents={docs}
        loading={documents.isLoading}
        health={health.data}
        scope={activeScope}
        onScopeChange={setScope}
        onUpload={upload}
        uploadErrors={uploadErrors}
        onDismissErrors={() => setUploadErrors([])}
        onChanged={() => documents.mutate()}
      />
    </div>
  );
}
