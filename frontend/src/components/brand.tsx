/** Wordmark: the product name in Latin and Devanagari (अक्षर = "letter, syllable"). */
export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-baseline gap-2 ${className}`}>
      <span className="text-[1.2rem] font-[680] tracking-[-0.01em] text-ink" style={{ fontStretch: "110%" }}>
        Akshara
      </span>
      <span lang="hi" className="text-[0.95rem] font-medium text-turmeric">
        अक्षर
      </span>
    </span>
  );
}

export function Spinner({ className = "size-4" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
