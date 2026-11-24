"use client";

import { Check, LibraryBig, LogOut, Monitor, Moon, Pencil, SquarePen, Sun, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Spinner, Wordmark } from "@/components/brand";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { applyTheme, readThemePref, type ThemePref } from "@/lib/theme";
import type { ConversationInfo, DocumentInfo, User } from "@/lib/types";

type Props = {
  user: User;
  conversations: ConversationInfo[] | undefined;
  activeId: string | null;
  documents: DocumentInfo[];
  open: boolean;
  onClose: () => void;
  onOpenLibrary: () => void;
  onChanged: () => void;
};

function groupByDate(items: ConversationInfo[]) {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const day = 86_400_000;
  const groups: { label: string; items: ConversationInfo[] }[] = [
    { label: "Today", items: [] },
    { label: "Yesterday", items: [] },
    { label: "Previous 7 days", items: [] },
    { label: "Older", items: [] },
  ];
  for (const c of items) {
    const t = new Date(c.updated_at).getTime();
    const idx = t >= startOfToday.getTime() ? 0 : t >= startOfToday.getTime() - day ? 1 : t >= startOfToday.getTime() - 7 * day ? 2 : 3;
    groups[idx].items.push(c);
  }
  return groups.filter((g) => g.items.length);
}

export function Sidebar({ user, conversations, activeId, documents, open, onClose, onOpenLibrary, onChanged }: Props) {
  const processing = documents.filter((d) => d.status === "processing").length;
  const readyCount = documents.filter((d) => d.status === "ready").length;

  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-scrim lg:hidden" onClick={onClose} aria-hidden="true" />}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[280px] flex-col border-r border-line bg-sidebar transition-transform duration-200 lg:static lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-label="Conversations"
      >
        <div className="flex items-center justify-between px-4 pb-3 pt-4">
          <Link href="/" onClick={onClose} aria-label="Akshara home">
            <Wordmark />
          </Link>
          <button className="rounded-lg p-1.5 text-ink-soft hover:bg-wash lg:hidden" onClick={onClose} aria-label="Close menu">
            <X className="size-5" />
          </button>
        </div>

        <div className="px-3">
          <Link
            href="/"
            onClick={onClose}
            className="flex items-center gap-2.5 rounded-[10px] border border-line bg-raised px-3 py-2 font-medium text-ink transition-colors hover:border-indigo/40"
          >
            <SquarePen className="size-[18px] text-indigo" />
            New chat
          </Link>
        </div>

        <nav className="scroll-area mt-4 flex-1 overflow-y-auto px-3 pb-4">
          {conversations === undefined ? (
            <div className="flex justify-center py-6 text-ink-faint">
              <Spinner />
            </div>
          ) : conversations.length === 0 ? (
            <p className="px-2 text-sm text-ink-faint">Your conversations will appear here.</p>
          ) : (
            groupByDate(conversations).map((group) => (
              <div key={group.label} className="mb-4">
                <h2 className="px-2 pb-1 text-[0.8rem] font-medium text-ink-faint">{group.label}</h2>
                <ul>
                  {group.items.map((c) => (
                    <ConversationRow key={c.id} conv={c} active={c.id === activeId} onNavigate={onClose} onChanged={onChanged} />
                  ))}
                </ul>
              </div>
            ))
          )}
        </nav>

        <div className="border-t border-line p-3">
          <button
            onClick={() => {
              onOpenLibrary();
              onClose();
            }}
            className="flex w-full items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-left hover:bg-wash"
          >
            <LibraryBig className="size-[18px] text-indigo" />
            <span className="flex-1 font-medium">Library</span>
            {processing > 0 ? (
              <span className="flex items-center gap-1.5 text-sm text-turmeric">
                <Spinner className="size-3.5" /> {processing}
              </span>
            ) : (
              <span className="text-sm text-ink-faint">{readyCount}</span>
            )}
          </button>
          <UserRow user={user} />
        </div>
      </aside>
    </>
  );
}

function ConversationRow({
  conv,
  active,
  onNavigate,
  onChanged,
}: {
  conv: ConversationInfo;
  active: boolean;
  onNavigate: () => void;
  onChanged: () => void;
}) {
  const router = useRouter();
  const [mode, setMode] = useState<"view" | "rename" | "confirm">("view");
  const [title, setTitle] = useState(conv.title);

  async function rename() {
    const next = title.trim();
    setMode("view");
    if (!next || next === conv.title) return setTitle(conv.title);
    await api(`/api/conversations/${conv.id}`, { method: "PATCH", json: { title: next } }).catch(() => setTitle(conv.title));
    onChanged();
  }

  async function remove() {
    await api(`/api/conversations/${conv.id}`, { method: "DELETE" }).catch(() => undefined);
    onChanged();
    if (active) router.push("/");
  }

  if (mode === "rename") {
    return (
      <li className="flex items-center gap-1 rounded-[10px] bg-wash px-2 py-1">
        <input
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") rename();
            if (e.key === "Escape") {
              setTitle(conv.title);
              setMode("view");
            }
          }}
          onBlur={rename}
          className="min-w-0 flex-1 bg-transparent py-1 text-[0.95rem] focus:outline-none"
          aria-label="Conversation title"
        />
        <Check className="size-4 text-ink-soft" aria-hidden="true" />
      </li>
    );
  }

  if (mode === "confirm") {
    return (
      <li className="rounded-[10px] bg-rose-wash px-2.5 py-2 text-sm">
        <p className="text-rose">Delete this chat?</p>
        <div className="mt-1.5 flex gap-2">
          <button onClick={remove} className="rounded-md bg-rose px-2.5 py-1 font-semibold text-white">
            Delete
          </button>
          <button onClick={() => setMode("view")} className="rounded-md px-2.5 py-1 text-ink-soft hover:bg-raised">
            Cancel
          </button>
        </div>
      </li>
    );
  }

  return (
    <li className="group relative">
      <Link
        href={`/c/${conv.id}`}
        onClick={onNavigate}
        aria-current={active ? "page" : undefined}
        className={`block truncate rounded-[10px] py-2 pl-2.5 pr-16 text-[0.95rem] transition-colors ${
          active ? "bg-wash font-medium text-indigo" : "text-ink hover:bg-wash/70"
        }`}
        title={conv.title}
      >
        {conv.title}
      </Link>
      <div
        className={`absolute inset-y-0 right-1 flex items-center gap-0.5 ${
          active ? "flex" : "hidden group-focus-within:flex group-hover:flex"
        }`}
      >
        <button onClick={() => setMode("rename")} className="rounded-md p-1.5 text-ink-faint hover:bg-raised hover:text-ink" aria-label={`Rename ${conv.title}`}>
          <Pencil className="size-3.5" />
        </button>
        <button onClick={() => setMode("confirm")} className="rounded-md p-1.5 text-ink-faint hover:bg-raised hover:text-rose" aria-label={`Delete ${conv.title}`}>
          <Trash2 className="size-3.5" />
        </button>
      </div>
    </li>
  );
}

function UserRow({ user }: { user: User }) {
  const { logout } = useAuth();
  const [theme, setTheme] = useState<ThemePref>("system");
  useEffect(() => setTheme(readThemePref()), []);

  const next: Record<ThemePref, ThemePref> = { system: "light", light: "dark", dark: "system" };
  const ThemeIcon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;
  const themeLabel = { system: "System theme", light: "Light theme", dark: "Dark theme" }[theme];

  return (
    <div className="mt-1 flex items-center gap-2 rounded-[10px] px-2.5 py-2">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-indigo text-sm font-semibold text-on-indigo">
        {user.name.slice(0, 1).toUpperCase()}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">{user.name}</span>
        <span className="block truncate text-xs text-ink-faint">{user.email}</span>
      </span>
      <button
        onClick={() => {
          const t = next[theme];
          setTheme(t);
          applyTheme(t);
        }}
        className="rounded-md p-1.5 text-ink-soft hover:bg-wash"
        aria-label={`${themeLabel}. Switch theme`}
        title={themeLabel}
      >
        <ThemeIcon className="size-4" />
      </button>
      <button onClick={logout} className="rounded-md p-1.5 text-ink-soft hover:bg-wash" aria-label="Sign out" title="Sign out">
        <LogOut className="size-4" />
      </button>
    </div>
  );
}
