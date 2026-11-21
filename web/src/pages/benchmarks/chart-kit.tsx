import { useEffect, useState, type ReactNode } from "react"
import { ReferenceArea } from "recharts"
import { bandRanges, bandStrength } from "./lib"
import type { Band } from "./types"

/** Tooltip card in the shadcn chart style; `render` gets the hovered datum. */
export function PointTip<T>({ active, payload, render }: { active?: boolean; payload?: readonly { payload?: unknown }[]; render: (d: T) => ReactNode }) {
  const d = payload?.[0]?.payload as T | undefined
  if (!active || !d) return null
  return <div className="grid min-w-40 gap-1 rounded-lg border border-border/50 bg-background px-2.5 py-2 text-xs shadow-xl">{render(d)}</div>
}

/** One "label  value" line inside a tooltip. */
export function TipRow({ k, children }: { k: ReactNode; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted-foreground">{k}</span>
      <span className="font-mono font-medium text-foreground tabular-nums">{children}</span>
    </div>
  )
}

export function useWide(min = 768) {
  const q = `(min-width: ${min}px)`
  const [wide, setWide] = useState(() => typeof window !== "undefined" && window.matchMedia(q).matches)
  useEffect(() => {
    const m = window.matchMedia(q)
    const h = () => setWide(m.matches)
    m.addEventListener("change", h)
    return () => m.removeEventListener("change", h)
  }, [q])
  return wide
}

/** UZP points bands as shaded ReferenceAreas (call as a function inside the chart). */
export function bandAreas(bands: Band[], lo: number, hi: number, showLabels = true) {
  return bandRanges(bands, lo, hi).map((b) => (
    <ReferenceArea
      key={b.points}
      x1={b.x1}
      x2={b.x2}
      ifOverflow="hidden"
      fill="var(--sage)"
      fillOpacity={bandStrength(b.points) * 0.9}
      strokeOpacity={0}
      label={showLabels ? { value: `${b.points} pkt`, position: "top", fontSize: 11, fontWeight: 600, fill: b.points ? "var(--success)" : "var(--muted-foreground)" } : undefined}
    />
  ))
}

export function LegendDot({ color, children }: { color: string; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="size-2 rounded-full" style={{ background: color }} />
      {children}
    </span>
  )
}

/** Value label to the right of a horizontal bar, never wrapped (Recharts' default label wraps near the edge). */
export function RightLabel(p: { x?: number | string; y?: number | string; width?: number | string; height?: number | string; value?: unknown }) {
  if (p.value == null || p.value === "") return null
  return (
    <text x={Number(p.x) + Number(p.width ?? 0) + 8} y={Number(p.y) + Number(p.height ?? 0) / 2} dominantBaseline="central" className="fill-muted-foreground" fontSize={12}>
      {String(p.value)}
    </text>
  )
}
