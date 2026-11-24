"use client";

import { AlertTriangle, FileSpreadsheet, FileText, FileType2, Trash2, Upload, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Spinner } from "@/components/brand";
import { api } from "@/lib/api";
import { languageName } from "@/lib/language";
import type { DocumentInfo, Health } from "@/lib/types";

type Props = {
  open: boolean;
  onClose: () => void;
  documents: DocumentInfo[];
  loading: boolean;
  health: Health | undefined;
  scope: string[];
  onScopeChange: (ids: string[]) => void;
  onUpload: (files: File[]) => void;
  uploadErrors: string[];
  onDismissErrors: () => void;
  onChanged: () => void;
};

const OCR_NAMES: Record<string, string> = {
  hin: "Hindi", tam: "Tamil", tel: "Telugu", kan: "Kannada", mal: "Malayalam", ben: "Bengali", guj: "Gujarati",
  pan: "Punjabi", mar: "Marathi", ori: "Odia", urd: "Urdu", asm: "Assamese", nep: "Nepali", san: "Sanskrit",
};

function size(bytes: number) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function LibraryPanel(props: Props) {
  const { open, onClose, documents, loading, health, scope, onScopeChange, onUpload, uploadErrors, onDismissErrors, onChanged } = props;
  const [over, setOver] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const ocrLangs = (health?.ocr.languages ?? []).filter((l) => l !== "eng").map((l) => OCR_NAMES[l] ?? l);
  const toggle = (id: string) => onScopeChange(scope.includes(id) ? scope.filter((x) => x !== id) : [...scope, id]);

  return (
    <>
      <div className="fixed inset-0 z-30 bg-scrim xl:hidden" onClick={onClose} aria-hidden="true" />
      <aside
        className="fixed inset-y-0 right-0 z-40 flex w-full max-w-[400px] flex-col border-l border-line bg-paper xl:static xl:z-auto xl:w-[380px]"
        aria-label="Library"
      >
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-line px-5">
          <h2 className="text-lg font-semibold" style={{ fontStretch: "105%" }}>
            Library
          </h2>
          <button ref={closeRef} onClick={onClose} className="rounded-lg p-1.5 text-ink-soft hover:bg-wash" aria-label="Close library">
            <X className="size-5" />
          </button>
        </div>

        <div className="scroll-area flex-1 overflow-y-auto px-5 py-5">
          <label
            onDragOver={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setOver(true);
            }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setOver(false);
              onUpload(Array.from(e.dataTransfer.files));
            }}
            className={`flex cursor-pointer flex-col items-center rounded-[14px] border-2 border-dashed px-4 py-6 text-center transition-colors focus-within:outline-2 focus-within:outline-ring ${
              over ? "border-indigo bg-wash" : "border-line hover:border-indigo/50"
            }`}
          >
            <Upload className="size-6 text-indigo" />
            <span className="mt-2 font-semibold">Drop files or choose them</span>
            <span className="mt-1 text-sm text-ink-faint">
              PDF, Word, text or CSV, up to {health?.limits.max_upload_mb ?? 25} MB each
            </span>
            <input
              type="file"
              multiple
              accept=".pdf,.docx,.txt,.md,.csv"
              className="sr-only"
              onChange={(e) => {
                onUpload(Array.from(e.target.files ?? []));
                e.target.value = "";
              }}
            />
          </label>
          {ocrLangs.length > 0 && (
            <p className="mt-2.5 text-sm text-ink-faint">
              Scanned pages and PDFs with broken fonts are read with OCR in {ocrLangs.join(", ")} and English.
            </p>
          )}

          {uploadErrors.length > 0 && (
            <div role="alert" className="mt-4 rounded-[10px] bg-rose-wash px-3.5 py-2.5 text-sm text-rose">
              <ul className="space-y-1">
                {uploadErrors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
              <button onClick={onDismissErrors} className="mt-1.5 font-semibold underline-offset-2 hover:underline">
                Dismiss
              </button>
            </div>
          )}

          <div className="mt-7 flex items-baseline justify-between">
            <h3 className="font-semibold">Your documents</h3>
            {scope.length > 0 && (
              <button onClick={() => onScopeChange([])} className="text-sm text-indigo hover:underline">
                Search all instead
              </button>
            )}
          </div>
          <p className="mt-0.5 text-sm text-ink-faint">
            {scope.length
              ? `Chat searches only the ${scope.length} selected.`
              : "Chat searches all of them. Tick documents to narrow it down."}
          </p>

          {loading ? (
            <div className="flex justify-center py-8 text-ink-faint">
              <Spinner />
            </div>
          ) : documents.length === 0 ? (
            <p className="mt-4 text-ink-soft">Nothing here yet. Add a file above to start asking questions about it.</p>
          ) : (
            <ul className="mt-3 divide-y divide-line">
              {documents.map((doc) => (
                <DocumentRow key={doc.id} doc={doc} selected={scope.includes(doc.id)} onToggle={() => toggle(doc.id)} onChanged={onChanged} />
              ))}
            </ul>
          )}
        </div>
      </aside>
    </>
  );
}

function DocIcon({ filename }: { filename: string }) {
  const ext = filename.split(".").pop()?.toLowerCase();
  const Icon = ext === "csv" ? FileSpreadsheet : ext === "pdf" ? FileType2 : FileText;
  return <Icon className="size-5 text-indigo" aria-hidden="true" />;
}

function DocumentRow({
  doc,
  selected,
  onToggle,
  onChanged,
}: {
  doc: DocumentInfo;
  selected: boolean;
  onToggle: () => void;
  onChanged: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const details = [
    languageName(doc.language),
    doc.page_count ? `${doc.page_count} page${doc.page_count === 1 ? "" : "s"}` : null,
    doc.chunk_count ? `${doc.chunk_count} passages` : null,
    size(doc.size_bytes),
  ].filter(Boolean);

  return (
    <li className="py-3">
      <div className="flex items-start gap-3">
        {doc.status === "ready" ? (
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            className="mt-1 size-4 shrink-0 accent-[var(--indigo)]"
            aria-label={`Search only selected documents: ${doc.filename}`}
          />
        ) : (
          <span className="mt-0.5 shrink-0">
            <DocIcon filename={doc.filename} />
          </span>
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium" title={doc.filename}>
            {doc.filename}
          </p>
          {doc.status === "processing" && (
            <p className="mt-0.5 flex items-center gap-1.5 text-sm text-turmeric">
              <Spinner className="size-3.5" /> Reading and indexing
            </p>
          )}
          {doc.status === "ready" && <p className="mt-0.5 text-sm text-ink-faint">{details.join(", ")}</p>}
          {doc.status === "ready" && doc.ocr_pages > 0 && (
            <p className="mt-0.5 text-sm text-ink-faint">
              {doc.ocr_pages} page{doc.ocr_pages === 1 ? "" : "s"} read with OCR
            </p>
          )}
          {doc.status === "failed" && <p className="mt-0.5 text-sm text-rose">{doc.error || "Couldn't read this file."}</p>}
          {doc.warnings?.map((w) => (
            <p key={w} className="mt-1 flex gap-1.5 text-sm text-amber">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
              {w}
            </p>
          ))}
          {confirming && (
            <div className="mt-2 flex items-center gap-2 text-sm">
              <span className="text-rose">Delete this document?</span>
              <button
                disabled={deleting}
                onClick={async () => {
                  setDeleting(true);
                  await api(`/api/documents/${doc.id}`, { method: "DELETE" }).catch(() => undefined);
                  onChanged();
                }}
                className="rounded-md bg-rose px-2.5 py-1 font-semibold text-white disabled:opacity-60"
              >
                Delete
              </button>
              <button onClick={() => setConfirming(false)} className="rounded-md px-2 py-1 text-ink-soft hover:bg-wash">
                Cancel
              </button>
            </div>
          )}
        </div>
        {!confirming && (
          <button
            onClick={() => setConfirming(true)}
            className="rounded-md p-1.5 text-ink-faint hover:bg-wash hover:text-rose"
            aria-label={`Delete ${doc.filename}`}
          >
            <Trash2 className="size-4" />
          </button>
        )}
      </div>
    </li>
  );
}
