import { CartesianGrid, LabelList, Scatter, ScatterChart, XAxis, YAxis } from "recharts"
import { Card, CardContent } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart"
import { bandAreas, LegendDot, PointTip, TipRow, useWide } from "./chart-kit"
import { f1s, fmt, logTicks, pb, pointsFor, usd } from "./lib"
import type { Band, BenchModel } from "./types"

const config = {
  chosen: { label: "Wybrany (profil Auto)", color: "var(--primary)" },
  rules: { label: "Reguły YAML", color: "var(--sage)" },
  other: { label: "Inne modele", color: "var(--foreground)" },
} satisfies ChartConfig

const LO = 0.75, HI = 8000, FLOOR = 0.9855

type Pt = { x: number; y: number; m: BenchModel; labelR: string; labelL: string }

/** Label centred above a point (Recharts' own "top" label wraps to the symbol width). */
function TopLabel(p: { x?: number | string; y?: number | string; width?: number | string; value?: unknown }) {
  if (!p.value) return null
  return (
    <text x={Number(p.x) + Number(p.width ?? 0) / 2} y={Number(p.y) - 8} textAnchor="middle" className="fill-foreground" fontSize={11.5} fontWeight={500}>
      {String(p.value)}
    </text>
  )
}

const short = (m: BenchModel) => m.name.replace(/ \(.*\)/, "")

/** F1 (train) vs total parameters, log axis, over the UZP points bands. Rules (0 params) sit at the left edge. */
export function SizeScatter({ models, bands }: { models: BenchModel[]; bands: Band[] }) {
  const wide = useWide()
  const pts: Pt[] = models
    .filter((m) => m.params_b != null && m.f1.train != null)
    .sort((a, b) => a.params_b! - b.params_b!)
    .map((m) => ({ x: Math.max(1, m.params_b!), y: Math.max(FLOOR, m.f1.train!), m, labelR: "", labelL: "" }))
  // one label per cluster: points almost on top of each other share a label
  const groups: Pt[][] = []
  for (const p of pts) {
    const g = groups.find((g) => Math.log10(p.x) - Math.log10(g[0].x) < 0.1 && Math.abs(p.y - g[0].y) < 0.0008)
    if (g) g.push(p)
    else groups.push([p])
  }
  groups.forEach((g, i) => {
    const text = g.map((p) => short(p.m)).join(" · ") + (g[0].m.f1.train! < FLOOR ? ` ↓ ${f1s(g[0].m.f1.train)}` : "")
    // put the label on the left when the next point on the same row is too close on the right
    const next = groups.slice(i + 1).find((h) => Math.abs(h[0].y - g[0].y) < 0.0008)
    const crowded = next && Math.log10(next[0].x) - Math.log10(g[0].x) < 0.45
    if (crowded) g[0].labelL = text
    else g[0].labelR = text
  })
  const series = (k: keyof typeof config) =>
    pts.filter((p) => (k === "rules" ? p.m.arch === "rules" : k === "chosen" ? p.m.chosen : p.m.arch !== "rules" && !p.m.chosen))
  const unknown = models.filter((m) => m.params_b == null)
  return (
    <Card>
      <CardContent>
        <ChartContainer config={config} className="aspect-auto h-[300px] w-full sm:h-[380px]">
          <ScatterChart margin={{ top: 24, right: wide ? 24 : 8, bottom: 8, left: 0 }}>
            {bandAreas(bands, LO, HI, wide)}
            <CartesianGrid vertical={false} />
            <XAxis
              type="number"
              dataKey="x"
              scale="log"
              domain={[LO, HI]}
              ticks={logTicks(LO, HI)}
              tickFormatter={(v: number) => (v === 1 ? "0" : pb(v))}
              tickLine={false}
              axisLine={false}
              allowDataOverflow
            />
            <YAxis
              type="number"
              dataKey="y"
              domain={[0.985, 1.0015]}
              ticks={[0.985, 0.99, 0.995, 1]}
              tickFormatter={(v: number) => (v === 0.985 ? "<0,985" : fmt(v, 3)!)}
              tickLine={false}
              axisLine={false}
              width={56}
              allowDataOverflow
            />
            <ChartTooltip
              cursor={false}
              content={
                <PointTip<Pt>
                  render={({ m }) => (
                    <>
                      <div className="font-medium">
                        {m.name}
                        {m.vendor && <span className="font-normal text-muted-foreground"> · {m.vendor}</span>}
                      </div>
                      <TipRow k="Parametry">
                        {pb(m.params_b)}
                        {m.active_b != null && m.active_b !== m.params_b ? ` (aktywne ${pb(m.active_b)})` : ""}
                      </TipRow>
                      <TipRow k="F1 trening">{f1s(m.f1.train)}</TipRow>
                      {m.f1.blind != null && <TipRow k="F1 ślepy">{f1s(m.f1.blind)}</TipRow>}
                      <TipRow k="Koszt 36 dok.">{usd(m.cost_usd?.train) ?? "—"}</TipRow>
                      <TipRow k="Punkty UZP">{pointsFor(m.params_b, bands) ?? "—"}</TipRow>
                    </>
                  )}
                />
              }
            />
            {(Object.keys(config) as (keyof typeof config)[]).map((k) => (
              <Scatter key={k} data={series(k)} fill={`var(--color-${k})`} isAnimationActive={false}>
                {wide && <LabelList dataKey="labelR" position="right" offset={8} className="fill-foreground" fontSize={11.5} fontWeight={500} />}
                {wide && <LabelList dataKey="labelL" content={TopLabel} />}
              </Scatter>
            ))}
          </ScatterChart>
        </ChartContainer>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {(Object.keys(config) as (keyof typeof config)[]).map((k) => (
            <LegendDot key={k} color={config[k].color}>
              {config[k].label}
            </LegendDot>
          ))}
          {unknown.length > 0 && <span>Bez znanego rozmiaru: {unknown.map((m) => `${m.name} (F1 ${f1s(m.f1.train) ?? "—"})`).join(", ")}</span>}
        </div>
      </CardContent>
    </Card>
  )
}
