"use client";

import { FileUp } from "lucide-react";
import { Spinner } from "@/components/brand";
import { ScriptStack } from "@/components/script-stack";
import type { DocumentInfo } from "@/lib/types";

const SUGGESTIONS = [
  { lang: "en", text: "Summarize the main ideas, with page numbers" },
  { lang: "en", text: "List every person, place and date mentioned" },
  { lang: "hi", text: "इस दस्तावेज़ का सारांश हिंदी में दीजिए" },
  { lang: "ta", text: "இந்த ஆவணத்தின் முக்கிய கருத்துகள் என்ன?" },
];

type Props = {
  documents: DocumentInfo[];
  onUpload: (files: File[]) => void;
  onAsk: (text: string) => void;
  onOpenLibrary: () => void;
};

export function EmptyState({ documents, onUpload, onAsk, onOpenLibrary }: Props) {
  const ready = documents.filter((d) => d.status === "ready");
  const processing = documents.filter((d) => d.status === "processing");

  return (
    // my-auto (not justify-center) so tall content scrolls instead of being clipped at the top
    <div className="mx-auto flex min-h-full max-w-3xl flex-col px-5 py-10 sm:px-8">
      <div className="my-auto">
        <ScriptStack size="md" />

        {ready.length === 0 ? (
          <div className="mt-10 max-w-[52ch]">
            {processing.length > 0 ? (
              <p className="flex items-center gap-2 text-ink-soft">
                <Spinner className="size-4 text-turmeric" />
                Reading {processing[0].filename}
                {processing.length > 1 ? ` and ${processing.length - 1} more` : ""}. You can ask as soon as it&apos;s ready.
              </p>
            ) : (
              <>
                <p className="text-[1.05rem] text-ink-soft">
                  Add a document to begin: PDF, Word, text or CSV, in English or any of 22 Indian languages. Scanned pages
                  are read with OCR.
                </p>
                <label className="mt-6 inline-flex cursor-pointer items-center gap-2 rounded-[10px] bg-indigo px-4 py-2.5 font-semibold text-on-indigo transition-colors hover:bg-indigo-strong focus-within:outline-2 focus-within:outline-ring">
                  <FileUp className="size-[18px]" />
                  Upload a document
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
              </>
            )}
          </div>
        ) : (
          <div className="mt-10">
            <p className="text-ink-soft">
              Ask about{" "}
              <button onClick={onOpenLibrary} className="font-medium text-indigo underline-offset-4 hover:underline">
                {ready.length === 1 ? ready[0].filename : `your ${ready.length} documents`}
              </button>{" "}
              in whichever language you like. Try one of these:
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s.text}
                  lang={s.lang}
                  onClick={() => onAsk(s.text)}
                  className="rounded-[10px] border border-line px-3.5 py-2 text-left text-[0.95rem] text-ink transition-colors hover:border-indigo/50 hover:bg-wash"
                >
                  {s.text}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
