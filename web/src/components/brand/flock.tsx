import { cn } from "@/lib/utils"

type Bird = { y: string; dur: number; delay: number; scale: number }

const DEFAULT: Bird[] = [
  { y: "12%", dur: 15, delay: -2, scale: 0.9 },
  { y: "22%", dur: 19, delay: -9, scale: 0.6 },
  { y: "8%", dur: 23, delay: -15, scale: 0.45 },
  { y: "70%", dur: 27, delay: -5, scale: 0.5 },
  { y: "30%", dur: 17, delay: -12, scale: 0.75 },
]

/** A flying sparrow; wings flap with CSS (see .sparrow-wing in index.css). */
export function FlyingSparrow({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 64 40" aria-hidden="true" className={cn("h-10 w-16", className)} style={style}>
      <path d="M50 21l13-4-2 7z" fill="#6b4a33" />
      <ellipse cx="34" cy="22" rx="17" ry="8" fill="#a8703f" />
      <path d="M20 24q8 7 22 3-12 0-17-5z" fill="#efe3cf" />
      <circle cx="18" cy="17" r="7" fill="#9c9389" />
      <path d="M12 15q4-7 11-2-3 1-5 1z" fill="#8a4a25" />
      <circle cx="16" cy="16" r="1.2" fill="#1a1310" />
      <path d="M11 17l-5 1.5 5 1z" fill="#3a2b22" />
      <path className="sparrow-wing" d="M30 19q8-16 22-15-6 9-14 17z" fill="#7a4f2e" />
    </svg>
  )
}

/** Sparrows crossing the parent (which must be position:relative + overflow:hidden). */
export function Flock({ birds = DEFAULT, className }: { birds?: Bird[]; className?: string }) {
  return (
    <div aria-hidden="true" className={cn("flock-host pointer-events-none absolute inset-0 z-[2] motion-reduce:hidden", className)}>
      {birds.map((b, i) => (
        <div
          key={i}
          className="sparrow-fly absolute left-0"
          style={{ top: b.y, animationDuration: `${b.dur}s`, animationDelay: `${b.delay}s` }}
        >
          <FlyingSparrow style={{ transform: `scale(${-1.6 * b.scale}, ${1.6 * b.scale})` }} />
        </div>
      ))}
    </div>
  )
}
