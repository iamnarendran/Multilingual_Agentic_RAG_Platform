"use client";

import { AlertTriangle, Check, ChevronDown, Copy, ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";
import { useMemo, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { AgentTrace } from "@/components/agent-trace";
import { languageName } from "@/lib/language";
import type { ChatMessage, Source, Validation } from "@/lib/types";

export function UserMessage({ message }: { message: ChatMessage }) {
  const lang = message.language && message.language !== "en" ? languageName(message.language) : null;
  return (
    <div className="flex flex-col items-end">
      <div
        lang={message.language ?? undefined}
        className="max-w-[85%] whitespace-pre-wrap rounded-[18px] rounded-br-[6px] bg-wash px-4 py-2.5 text-ink"
      >
        {message.content}
      </div>
      {lang && <span className="mt-1 pr-1 text-xs text-ink-faint">{lang}</span>}
    </div>
  );
}

// "[1]" or "[1, 2]" -> markdown links the renderer turns into citation chips. Skip real links "[x](...)".
function linkCitations(text: string) {
  return text.replace(/\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\](?!\()/g, (_, nums: string) =>
    nums
      .split(/\s*,\s*/)
      .map((n) => `[${n}](#cite-${n})`)
      .join(""),
  );
}

function pageLabel(s: Source) {
  if (s.page == null) return null;
  return s.page_end && s.page_end !== s.page ? `pages ${s.page}–${s.page_end}` : `page ${s.page}`;
}

export function AssistantMessage({ message }: { message: ChatMessage }) {
  const live = message.status === "streaming";
  const [openSource, setOpenSource] = useState<number | null>(null);
  const byIndex = useMemo(() => new Map(message.sources.map((s) => [s.index, s])), [message.sources]);

  const components = useMemo<Components>(
    () => ({
      a({ href, children }) {
        const n = href?.startsWith("#cite-") ? Number(href.slice(6)) : NaN;
        const src = byIndex.get(n);
        if (!src) {
          if (!Number.isNaN(n)) return <span className="text-ink-faint">[{n}]</span>;
          return (
            <a href={href} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          );
        }
        return <CitationChip source={src} onOpen={() => setOpenSource(n)} />;
      },
    }),
    [byIndex],
  );

  const content = useMemo(() => linkCitations(message.content), [message.content]);
  const waiting = live && !message.content;

  return (
    <article className="flex gap-3" lang={message.language ?? undefined}>
      <span
        aria-hidden="true"
        lang="hi"
        className="mt-0.5 hidden size-7 shrink-0 items-center justify-center rounded-full bg-indigo text-[0.95rem] font-semibold text-on-indigo sm:flex"
      >
        अ
      </span>
      <div className="min-w-0 flex-1">
        <AgentTrace steps={message.steps} live={live} latencyMs={message.latencyMs} />

        {message.content && (
          <div className={`answer ${live ? "caret" : ""}`}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
              {content}
            </ReactMarkdown>
          </div>
        )}
        {waiting && !message.steps.length && <p className="text-ink-faint">Starting…</p>}

        {message.error && (
          <p role="alert" className="mt-3 flex gap-2 rounded-[10px] bg-rose-wash px-3.5 py-2.5 text-sm text-rose">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            {message.error}
          </p>
        )}
        {message.status === "stopped" && (
          <p className="mt-2 text-sm text-ink-faint">Stopped. The partial answer is saved in this chat.</p>
        )}

        {message.sources.length > 0 && !live && (
          <SourceList sources={message.sources} open={openSource} onToggle={(n) => setOpenSource(openSource === n ? null : n)} />
        )}

        {!live && message.content && (
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
            {message.validation && <ValidationBadge validation={message.validation} />}
            <CopyButton text={message.content} />
          </div>
        )}
      </div>
    </article>
  );
}

function CitationChip({ source, onOpen }: { source: Source; onOpen: () => void }) {
  const page = pageLabel(source);
  const [below, setBelow] = useState(false);
  // Open the preview below the marker when there isn't room above it.
  const place = (el: HTMLElement) => setBelow(el.getBoundingClientRect().top < 220);
  return (
    <span
      className="group relative inline-block align-baseline"
      onMouseEnter={(e) => place(e.currentTarget)}
      onFocus={(e) => place(e.currentTarget)}
    >
      <button
        type="button"
        onClick={onOpen}
        className="cite mx-[1px] inline-flex h-[1.15rem] min-w-[1.15rem] -translate-y-[1px] items-center justify-center rounded-[5px] bg-turmeric-wash px-1 text-[0.72rem] font-bold leading-none text-turmeric hover:bg-turmeric hover:text-paper"
        aria-label={`Source ${source.index}: ${source.filename}${page ? `, ${page}` : ""}`}
      >
        {source.index}
      </button>
      <span
        role="tooltip"
        className={`pointer-events-none invisible absolute left-1/2 z-30 w-72 max-w-[80vw] -translate-x-1/2 ${below ? "top-full mt-2" : "bottom-full mb-2"} rounded-[12px] border border-line bg-raised p-3 text-left text-[0.84rem] leading-normal text-ink-soft opacity-0 shadow-[0_8px_30px_-12px_rgb(30_34_80/0.35)] transition-opacity group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100`}
      >
        <span className="block font-semibold text-ink">
          {source.filename}
          {page && <span className="font-normal text-ink-faint">, {page}</span>}
        </span>
        <span className="mt-1 line-clamp-4" lang={source.language ?? undefined}>
          {source.text}
        </span>
      </span>
    </span>
  );
}

function SourceList({ sources, open, onToggle }: { sources: Source[]; open: number | null; onToggle: (n: number) => void }) {
  return (
    <section className="mt-5" aria-label="Sources">
      <h3 className="mb-1.5 text-sm font-semibold text-ink-soft">Sources</h3>
      <ol className="divide-y divide-line border-y border-line">
        {sources.map((s) => {
          const expanded = open === s.index;
          const page = pageLabel(s);
          return (
            <li key={s.index}>
              <button
                onClick={() => onToggle(s.index)}
                aria-expanded={expanded}
                className="flex w-full items-start gap-3 py-2.5 text-left hover:bg-wash/50"
              >
                <span className="mt-0.5 flex h-5 min-w-5 items-center justify-center rounded-[5px] bg-turmeric-wash px-1 text-xs font-bold text-turmeric">
                  {s.index}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-ink">
                    {s.filename}
                    {page && <span className="font-normal text-ink-faint">, {page}</span>}
                  </span>
                  <span
                    lang={s.language ?? undefined}
                    className={`mt-0.5 text-sm text-ink-soft ${expanded ? "block whitespace-pre-line" : "line-clamp-2"}`}
                  >
                    {s.text}
                  </span>
                </span>
                <ChevronDown className={`mt-1 size-4 shrink-0 text-ink-faint transition-transform ${expanded ? "rotate-180" : ""}`} />
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function ValidationBadge({ validation }: { validation: Validation }) {
  const [open, setOpen] = useState(false);
  if (validation.grounded === null) {
    return (
      <span className="flex items-center gap-1.5 text-sm text-ink-faint" title={validation.error}>
        <ShieldQuestion className="size-4" /> Not verified
      </span>
    );
  }
  if (validation.grounded && validation.issues.length === 0) {
    return (
      <span className="flex items-center gap-1.5 text-sm text-leaf">
        <ShieldCheck className="size-4" /> Checked against the sources
      </span>
    );
  }
  const n = validation.issues.length;
  return (
    <div className="text-sm">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex items-center gap-1.5 text-amber hover:underline">
        <ShieldAlert className="size-4" />
        {n ? `${n} statement${n === 1 ? "" : "s"} may not be supported` : "Parts may not be supported"}
      </button>
      {open && n > 0 && (
        <ul className="mt-1.5 list-disc space-y-1 pl-6 text-ink-soft">
          {validation.issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          /* clipboard blocked */
        }
      }}
      className="flex items-center gap-1.5 text-sm text-ink-faint hover:text-ink"
    >
      {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}
