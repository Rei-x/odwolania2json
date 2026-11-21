import { useId } from "react"
import { cn } from "@/lib/utils"

type Bird = { y: string; dur: number; delay: number; scale: number }

const DEFAULT: Bird[] = [
  { y: "12%", dur: 15, delay: -2, scale: 0.9 },
  { y: "22%", dur: 19, delay: -9, scale: 0.6 },
  { y: "8%", dur: 23, delay: -15, scale: 0.45 },
  { y: "70%", dur: 27, delay: -5, scale: 0.5 },
  { y: "30%", dur: 17, delay: -12, scale: 0.75 },
]

const WING_ORIGIN: React.CSSProperties = { transformOrigin: "95px 57px" }

/** A flying house sparrow (faces left); wings flap with CSS (see .sparrow-wing in index.css). */
export function FlyingSparrow({ className, style }: { className?: string; style?: React.CSSProperties }) {
  const id = useId()
  return (
    <svg viewBox="0 0 200 120" aria-hidden="true" className={cn("h-12 w-20", className)} style={style}>
      <defs>
        <clipPath id={`${id}s`}>
          <path d="M26 42 C30 30 44 25 56 28 C64 30 70 35 75 40 C94 36 122 41 148 53 C162 50 178 46 194 46 C190 51 188 55 189 58.5 C188 62 190 66 194 70 C178 70 162 68 149 66 C133 76 111 82 89 82 C65 82 45 76 35 66 C27 59 24 50 26 42Z" />
        </clipPath>
        <linearGradient id={`${id}b`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#a8532f" />
          <stop offset="1" stopColor="#8c3f22" />
        </linearGradient>
        <linearGradient id={`${id}w`} x1="0" y1="1" x2=".8" y2="0">
          <stop offset="0" stopColor="#9b4628" />
          <stop offset="1" stopColor="#6b2c17" />
        </linearGradient>
      </defs>
      <path className="sparrow-wing" style={WING_ORIGIN} d="M100 50 C106 32 120 16 140 8 C146 6 152 7 156 9 C152 13 156 15 161 16 C156 20 158 23 163 25 C152 31 136 42 118 54Z" fill="#5a2614" />
      <g clipPath={`url(#${id}s)`}>
        <rect width="200" height="120" fill={`url(#${id}b)`} />
        <path d="M144 40 L200 40 L200 80 L144 80 C150 72 152 62 148 54Z" fill="#7d351d" />
        <path d="M152 57 C166 55 178 53 190 51 M152 61 C166 62 178 64 190 66" stroke="#3f281a" strokeWidth="1" fill="none" opacity=".6" />
        <ellipse cx="96" cy="94" rx="74" ry="22" fill="#ebdfcb" />
        <ellipse cx="44" cy="52" rx="21" ry="17" fill="#efe0c2" />
        <ellipse cx="50" cy="29" rx="27" ry="11" fill="#a04d2c" />
        <path d="M44 38 C57 35 69 39 78 46 C74 55 67 60 59 62 C60 51 55 43 44 38Z" fill="#8f3f24" />
        <path d="M24 52 C27 63 34 69 45 71 C47 63 43 56 36 52 C32 53 28 53 24 52Z" fill="#241a14" />
        <path d="M86 44 l11 3 M99 42 l12 4 M90 50 l10 2.5 M112 48 l10 3" stroke="#2a1d16" strokeWidth="2.2" strokeLinecap="round" />
      </g>
      <circle cx="37" cy="44" r="3.3" fill="#120d0a" />
      <circle cx="36" cy="43" r="1.1" fill="#fff" />
      <path d="M27.5 44.5 L14 48.8 L27.5 52.5 Z" fill="#3b2c22" />
      <path d="M27.5 48.6 L15.5 49 L27.5 52.5Z" fill="#594434" />
      <g className="sparrow-wing" style={WING_ORIGIN}>
        <path d="M84 57 C88 37 104 19 130 9 C136 7 144 6 149 8 C145 12 149 15 155 15 C151 19 153 23 159 24 C153 28 154 31 159 34 C147 40 128 50 107 63Z" fill={`url(#${id}w)`} />
        <path d="M131 12 C122 22 112 34 104 48 M141 13 C130 24 120 36 110 52 M148 19 C137 29 126 41 116 56" stroke="#3e2615" strokeWidth="1" fill="none" opacity=".55" />
        <path d="M86 55 C91 41 101 30 115 22 C110 33 103 44 96 58Z" fill="#b8673c" />
        <path d="M92 52 C99 42 108 33 119 27" stroke="#f6eddd" strokeWidth="2.2" strokeLinecap="round" fill="none" />
      </g>
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
          <FlyingSparrow style={{ transform: `scale(${-1.3 * b.scale}, ${1.3 * b.scale})` }} />
        </div>
      ))}
    </div>
  )
}
