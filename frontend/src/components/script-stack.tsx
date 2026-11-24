import { HERO_LINES } from "@/lib/language";

/**
 * The same question set in eight scripts, each at its own width on the Anek width axis.
 * This is the product's one loud typographic moment.
 */
export function ScriptStack({ size = "lg", lines = HERO_LINES.length }: { size?: "lg" | "md"; lines?: number }) {
  const fontSize = size === "lg" ? "clamp(1.55rem, 3.4vw, 2.5rem)" : "clamp(1.3rem, 2.4vw, 1.9rem)";
  return (
    <div aria-label="What does this document say? Written in several Indian languages" role="img">
      {HERO_LINES.slice(0, lines).map((line, i) => (
        <p
          key={line.lang}
          lang={line.lang}
          aria-hidden="true"
          className={`settle leading-[1.32] ${line.lang === "en" ? "text-ink" : "text-indigo"}`}
          style={{
            fontSize,
            fontStretch: `${line.width}%`,
            fontWeight: line.lang === "en" ? 640 : 560,
            animationDelay: `${i * 70}ms`,
            opacity: line.lang === "en" ? 1 : Math.max(0.45, 1 - Math.abs(i - 2) * 0.1),
          }}
        >
          {line.text}
        </p>
      ))}
    </div>
  );
}
