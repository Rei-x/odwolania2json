import { useEffect, useState, type ReactNode } from "react"
import { ReferenceArea } from "recharts"
import { SvgModelLogo } from "@/components/brand/model-logo"
import { SMALL_B } from "./lib"

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

/** Shaded "small model" zone (≤ 8B: runs on an own server) on a log size axis. */
export function smallArea(lo: number, showLabel = true) {
  return (
    <ReferenceArea
      x1={lo}
      x2={SMALL_B}
      ifOverflow="hidden"
      fill="var(--sage)"
      fillOpacity={0.13}
      strokeOpacity={0}
      label={showLabel ? { value: "≤ 8B · własny serwer", position: "top", fontSize: 11, fontWeight: 600, fill: "var(--success)" } : undefined}
    />
  )
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

/** Category-axis tick (horizontal bar charts): vendor logo + model name, right-aligned to the axis. */
export function LogoTick({ x, y, payload, ids, fontSize = 12.5 }: { x?: number | string; y?: number | string; payload?: { value?: unknown }; ids: Record<string, string>; fontSize?: number }) {
  const name = String(payload?.value ?? "")
  const X = Number(x), Y = Number(y)
  const w = name.length * fontSize * 0.6
  return (
    <g>
      <SvgModelLogo id={ids[name] ?? ""} name={name} x={X - w - 22} y={Y} size={14} />
      <text x={X - 4} y={Y} textAnchor="end" dominantBaseline="central" className="fill-foreground" fontSize={fontSize}>
        {name}
      </text>
    </g>
  )
}

/** Scatter label (logo + text) right of / above a point. `items` is the series' data, `text` picks the label. */
export function logoLabel<T extends { id: string; name: string }>(items: T[], text: (d: T) => string, side: "right" | "top") {
  return function LogoLabel(p: { x?: number | string; y?: number | string; width?: number | string; height?: number | string; index?: number }) {
    const d = p.index != null ? items[p.index] : undefined
    const t = d ? text(d) : ""
    if (!d || !t) return null
    const x = Number(p.x), y = Number(p.y), w = Number(p.width ?? 0), h = Number(p.height ?? 0)
    if (side === "top") {
      const tw = t.length * 6.3
      const lx = x + w / 2 - (tw + 18) / 2
      return (
        <g>
          <SvgModelLogo id={d.id} name={d.name} x={lx} y={y - 14} size={13} />
          <text x={lx + 18} y={y - 14} dominantBaseline="central" className="fill-foreground" fontSize={11.5} fontWeight={500} paintOrder="stroke" stroke="var(--card)" strokeWidth={4} strokeLinejoin="round">
            {t}
          </text>
        </g>
      )
    }
    const lx = x + w + 7
    return (
      <g>
        <SvgModelLogo id={d.id} name={d.name} x={lx} y={y + h / 2} size={13} />
        <text x={lx + 17} y={y + h / 2} dominantBaseline="central" className="fill-foreground" fontSize={11.5} fontWeight={500} paintOrder="stroke" stroke="var(--card)" strokeWidth={4} strokeLinejoin="round">
          {t}
        </text>
      </g>
    )
  }
}
