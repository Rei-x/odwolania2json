import { cn } from "@/lib/utils"

/** House sparrow mark used in the wordmark and favicon. */
export function SparrowMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn("size-7 shrink-0", className)}>
      <path d="M27 15l4-1-4 3z" fill="#6b4a33" />
      <ellipse cx="18" cy="18" rx="10" ry="8" fill="#a8703f" />
      <path d="M9 19q3 8 11 7-7-2-8-8z" fill="#efe3cf" />
      <path d="M15 14q7-4 12 3-5 5-11 2z" fill="#7a4f2e" />
      <circle cx="11" cy="12" r="6" fill="#9c9389" />
      <path d="M6 11q3-6 9-3-1 3-3 2z" fill="#8a4a25" />
      <path d="M6 14q2 3 5 3l-1-3z" fill="#2b211b" />
      <circle cx="9.5" cy="11.5" r="1.1" fill="#1a1310" />
      <path d="M5.5 12.5L3 13.5l2.8.8z" fill="#3a2b22" />
    </svg>
  )
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-extrabold tracking-tight", className)}>
      <SparrowMark />
      <span>
        Wróbel<span className="text-primary">ek</span>
      </span>
    </span>
  )
}
