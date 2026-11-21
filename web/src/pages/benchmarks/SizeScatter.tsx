import { CartesianGrid, LabelList, Scatter, ScatterChart, XAxis, YAxis } from "recharts"
import { ModelName } from "@/components/brand/model-logo"
import { Card, CardContent } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart"
import { LegendDot, logoLabel, PointTip, smallArea, TipRow, useWide } from "./chart-kit"
import { f1s, fmt, logTicks, pb, usd } from "./lib"
import type { BenchModel } from "./types"

const config = {
  chosen: { label: "Wybrany (profil Auto)", color: "var(--primary)" },
  rules: { label: "Reguły YAML", color: "var(--sage)" },
  other: { label: "Inne modele", color: "var(--foreground)" },
} satisfies ChartConfig

const LO = 0.75, HI = 8000, FLOOR = 0.9855

type Pt = { x: number; y: number; m: BenchModel; id: string; name: string; labelR: string; labelT: string }

const short = (m: BenchModel) => m.name.replace(/ \(.*\)/, "")

/** F1 (train) vs total parameters on a log axis. Rules (no LLM) sit at "0" on the left. */
export function SizeScatter({ models }: { models: BenchModel[] }) {
  const wide = useWide()
  const pts: Pt[] = models
    .filter((m) => m.params_b != null && m.f1.train != null)
    .sort((a, b) => a.params_b! - b.params_b!)
    .map((m) => ({ x: Math.max(1, m.params_b!), y: Math.max(FLOOR, m.f1.train!), m, id: m.id, name: m.name, labelR: "", labelT: "" }))
  // one label per cluster: dots almost on top of each other share a label
  const groups: Pt[][] = []
  for (const p of pts) {
    const g = groups.find((g) => Math.log10(p.x) - Math.log10(g[0].x) < 0.1 && Math.abs(p.y - g[0].y) < 0.0008)
    if (g) g.push(p)
    else groups.push([p])
  }
  groups.forEach((g, i) => {
    const text = g.map((p) => short(p.m)).join(" · ") + (g[0].m.f1.train! < FLOOR ? ` ↓ ${f1s(g[0].m.f1.train)}` : "")
    // label above the point when the next point on the same row is close on the right
    const next = groups.slice(i + 1).find((h) => Math.abs(h[0].y - g[0].y) < 0.0008)
    if (next && Math.log10(next[0].x) - Math.log10(g[0].x) < 0.6) g[0].labelT = text
    else g[0].labelR = text
  })
  const keys = Object.keys(config) as (keyof typeof config)[]
  const series = (k: keyof typeof config) =>
    pts.filter((p) => (k === "rules" ? p.m.arch === "rules" : k === "chosen" ? p.m.chosen : p.m.arch !== "rules" && !p.m.chosen))
  const unknown = models.filter((m) => m.params_b == null)
  return (
    <Card>
      <CardContent>
        <ChartContainer config={config} className="aspect-auto h-[300px] w-full sm:h-[380px]">
          <ScatterChart margin={{ top: 24, right: wide ? 24 : 8, bottom: 8, left: 0 }}>
            {smallArea(LO, wide)}
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
                        <ModelName id={m.id} name={m.name} />
                      </div>
                      <TipRow k="Parametry">
                        {m.params_b === 0 ? "bez LLM" : pb(m.params_b)}
                        {m.active_b != null && m.active_b !== m.params_b ? ` (aktywne ${pb(m.active_b)})` : ""}
                      </TipRow>
                      <TipRow k="F1 trening">{f1s(m.f1.train)}</TipRow>
                      {m.f1.blind != null && <TipRow k="F1 ślepy">{f1s(m.f1.blind)}</TipRow>}
                      <TipRow k="Koszt 36 dok.">{usd(m.cost_usd?.train) ?? "—"}</TipRow>
                    </>
                  )}
                />
              }
            />
            {keys.map((k) => {
              const data = series(k)
              return (
                <Scatter key={k} data={data} fill={`var(--color-${k})`} isAnimationActive={false}>
                  {wide && <LabelList dataKey="labelR" content={logoLabel(data, (d) => d.labelR, "right")} />}
                  {wide && <LabelList dataKey="labelT" content={logoLabel(data, (d) => d.labelT, "top")} />}
                </Scatter>
              )
            })}
          </ScatterChart>
        </ChartContainer>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {keys.map((k) => (
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
