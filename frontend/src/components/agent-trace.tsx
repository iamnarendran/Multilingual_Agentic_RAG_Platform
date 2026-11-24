"use client";

import { Check, ChevronDown, X } from "lucide-react";
import { useState } from "react";
import { Spinner } from "@/components/brand";
import type { Step } from "@/lib/types";

const AGENT_NAMES: Record<string, string> = {
  language: "Language",
  router: "Router",
  planner: "Planner",
  retriever: "Retriever",
  grader: "Grader",
  generator: "Generator",
  validator: "Validator",
};

function seconds(ms: number) {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/** Live view of the agents working; collapses to one line once the answer is done. */
export function AgentTrace({ steps, live, latencyMs }: { steps: Step[]; live: boolean; latencyMs: number | null }) {
  const [open, setOpen] = useState(false);
  if (!steps.length) return null;
  const expanded = live || open;
  const total = latencyMs ?? steps.reduce((sum, s) => sum + (s.ms ?? 0), 0);

  return (
    <div className="mb-3">
      {!live && (
        <button
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="flex items-center gap-1.5 rounded-md py-0.5 text-sm text-ink-faint hover:text-ink-soft"
        >
          <ChevronDown className={`size-4 transition-transform ${open ? "" : "-rotate-90"}`} />
          {steps.length} agent steps in {seconds(total)}
        </button>
      )}
      {expanded && (
        <ol className={`relative space-y-1.5 ${live ? "" : "mt-2"} border-l border-line pl-4`} aria-live="polite">
          {steps.map((step, i) => (
            <li key={`${step.agent}-${i}`} className="relative text-sm">
              <span className="absolute -left-[1.42rem] top-[0.2rem] flex size-[0.95rem] items-center justify-center rounded-full bg-paper">
                {step.status === "running" ? (
                  <Spinner className="size-3.5 text-turmeric" />
                ) : step.status === "error" ? (
                  <X className="size-3.5 text-rose" />
                ) : (
                  <Check className="size-3.5 text-leaf" />
                )}
              </span>
              <span className="font-semibold text-ink">{AGENT_NAMES[step.agent] ?? step.agent}</span>{" "}
              <span className="text-ink-soft">{step.status === "running" ? `${step.label}…` : step.summary || step.label}</span>
              {step.ms !== undefined && step.status !== "running" && (
                <span className="ml-1.5 text-ink-faint">{seconds(step.ms)}</span>
              )}
              <StepDetail step={step} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function StepDetail({ step }: { step: Step }) {
  if (step.status !== "done" || !step.data) return null;
  if (step.agent === "planner" && Array.isArray(step.data.queries)) {
    return (
      <ul className="mt-1 flex flex-wrap gap-1.5">
        {(step.data.queries as string[]).map((q) => (
          <li key={q} className="rounded-md bg-wash px-2 py-0.5 text-[0.8rem] text-ink-soft">
            {q}
          </li>
        ))}
      </ul>
    );
  }
  if (step.agent === "router" && step.data.rewritten && typeof step.data.standalone_question === "string") {
    return <p className="mt-0.5 text-[0.82rem] text-ink-faint">Read as: {step.data.standalone_question}</p>;
  }
  return null;
}
