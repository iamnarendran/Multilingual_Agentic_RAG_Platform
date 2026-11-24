"use client";

import { ArrowUp, Paperclip, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

type Props = {
  streaming: boolean;
  disabled?: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  onUpload: (files: File[]) => void;
};

export function Composer({ streaming, disabled, onSend, onStop, onUpload }: Props) {
  const [text, setText] = useState("");
  const area = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  // Grow with the text, up to a limit
  useEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [text]);

  function submit() {
    const value = text.trim();
    if (!value || streaming || disabled) return;
    onSend(value);
    setText("");
  }

  return (
    <div className="shrink-0 px-3 pb-3 pt-2 sm:px-6 sm:pb-5">
      <form
        className="mx-auto max-w-3xl rounded-[18px] border border-line bg-raised transition-[border-color,box-shadow] has-[textarea:focus-visible]:border-indigo/70 has-[textarea:focus-visible]:ring-[3px] has-[textarea:focus-visible]:ring-ring/15"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <label htmlFor="composer" className="sr-only">
          Ask a question
        </label>
        <textarea
          id="composer"
          ref={area}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            // isComposing: don't send while an Indic/IME keyboard is still composing a character
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Ask about your documents, in any language"
          className="scroll-area block max-h-[220px] w-full resize-none bg-transparent px-4 pb-1 pt-3.5 text-[1rem] leading-[1.6] text-ink placeholder:text-ink-faint focus:outline-none focus-visible:outline-none"
          disabled={disabled}
        />
        <div className="flex items-center justify-between px-2 pb-2">
          <button
            type="button"
            onClick={() => fileInput.current?.click()}
            className="flex items-center gap-1.5 rounded-[10px] px-2.5 py-2 text-sm text-ink-soft hover:bg-wash hover:text-ink"
          >
            <Paperclip className="size-4" />
            Add document
          </button>
          <input
            ref={fileInput}
            type="file"
            multiple
            accept=".pdf,.docx,.txt,.md,.csv"
            className="hidden"
            onChange={(e) => {
              onUpload(Array.from(e.target.files ?? []));
              e.target.value = "";
            }}
          />
          {streaming ? (
            <button
              type="button"
              onClick={onStop}
              className="flex size-9 items-center justify-center rounded-full bg-ink text-paper hover:opacity-85"
              aria-label="Stop answering"
              title="Stop"
            >
              <Square className="size-3.5 fill-current" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!text.trim() || disabled}
              className="flex size-9 items-center justify-center rounded-full bg-indigo text-on-indigo transition-colors hover:bg-indigo-strong disabled:bg-line disabled:text-ink-faint"
              aria-label="Send"
              title="Send"
            >
              <ArrowUp className="size-[18px]" strokeWidth={2.4} />
            </button>
          )}
        </div>
      </form>
      <p className="mx-auto mt-2 max-w-3xl px-2 text-center text-xs text-ink-faint">
        Answers come from your documents and cite them. Check the source for anything important.
      </p>
    </div>
  );
}
