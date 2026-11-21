import type { ReactNode } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { f1s, fmt, negRatio, pb } from "./lib"
import type { SweepRun } from "./types"

function Stat({ k, value, children }: { k: string; value: string; children: ReactNode }) {
  return (
    <Card size="sm">
      <CardContent>
        <div className="text-xs text-muted-foreground">{k}</div>
        <div className="mt-1 text-2xl font-semibold tracking-tight tabular-nums">{value}</div>
        <div className="mt-0.5 text-[13px] text-muted-foreground">{children}</div>
      </CardContent>
    </Card>
  )
}

/** Three findings the chart does not show directly (each appears only when the data supports it). */
export function SweepCallouts({ runs }: { runs: SweepRun[] }) {
  const ok = runs.filter((r) => r.fb != null)
  const best = ok.filter((r) => r.pts === 20 && r.eu).sort((a, b) => b.fb! - a.fb!)[0]
  const gap = ok
    .filter((r) => r.ft != null)
    .map((r) => ({ r, d: r.ft! - r.fb! }))
    .sort((a, b) => b.d - a.d)[0]
  const leaky = runs.filter((r) => {
    const n = negRatio(r.blind?.negatives_ok)
    return n != null && n.a < n.b
  })
  const cards: ReactNode[] = []
  if (best)
    cards.push(
      <Stat key="best" k="Najlepszy za 20 pkt z hostingiem w UE" value={f1s(best.fb)!}>
        {best.label} · {pb(best.params_b)}
      </Stat>,
    )
  if (gap && gap.d >= 0.01)
    cards.push(
      <Stat key="gap" k="Największy spadek trening → ślepy" value={"−" + fmt(gap.d, 3)}>
        {gap.r.label}
      </Stat>,
    )
  if (leaky.length)
    cards.push(
      <Stat key="neg" k="Przepuszcza dokumenty spoza zakresu" value={`${leaky.length} z ${runs.length}`}>
        {leaky.map((r) => r.label).join(", ")}
      </Stat>,
    )
  if (!cards.length) return null
  return <div className="grid gap-3 sm:grid-cols-3">{cards}</div>
}
