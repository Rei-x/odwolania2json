import { Bar, BarChart, Cell, LabelList, XAxis, YAxis } from "recharts"
import { Card, CardContent } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart"
import { LegendDot, LogoTick, PointTip, RightLabel, TipRow, useWide } from "./chart-kit"
import { f1s, pb, usd } from "./lib"
import type { BenchModel } from "./types"

const config = {
  chosen: { label: "Wybrany (profil Auto)", color: "var(--primary)" },
  rules: { label: "Reguły YAML", color: "var(--sage)" },
  other: { label: "Inne modele", color: "var(--chart-4)" },
} satisfies ChartConfig

type Row = { name: string; cost: number; m: BenchModel; key: keyof typeof config; tag: string }

/** API cost of the 36-document train run, cheapest first; model size next to each bar. */
export function CostBars({ models }: { models: BenchModel[] }) {
  const wide = useWide(640)
  const sized = models.filter((m) => m.params_b != null && m.arch !== "router")
  const rows: Row[] = sized
    .filter((m) => m.cost_usd?.train != null)
    .sort((a, b) => a.cost_usd!.train! - b.cost_usd!.train!)
    .map((m) => {
      return {
        name: m.name.replace(/ \(.*\)/, ""),
        cost: m.cost_usd!.train!,
        m,
        key: m.arch === "rules" ? "rules" : m.chosen ? "chosen" : "other",
        tag: `${m.cost_usd!.train === 0 ? "0 $" : usd(m.cost_usd!.train)} · ${m.params_b === 0 ? "bez LLM" : pb(m.params_b)}`,
      }
    })
  const ids = Object.fromEntries(rows.map((r) => [r.name, r.m.id]))
  const unmeasured = sized.filter((m) => m.cost_usd?.train == null)
  return (
    <Card>
      <CardContent>
        <ChartContainer config={config} className="aspect-auto w-full" style={{ height: rows.length * 34 + 8 }}>
          <BarChart data={rows} layout="vertical" margin={{ top: 0, right: wide ? 120 : 100, bottom: 0, left: 0 }} barCategoryGap={8}>
            <XAxis type="number" hide domain={[0, "dataMax"]} />
            <YAxis type="category" dataKey="name" width={wide ? 190 : 140} tickLine={false} axisLine={false} interval={0} tick={<LogoTick ids={ids} fontSize={wide ? 12.5 : 11} />} />
            <ChartTooltip
              cursor={{ fill: "var(--muted)", opacity: 0.6 }}
              content={
                <PointTip<Row>
                  render={({ m }) => (
                    <>
                      <div className="font-medium">{m.name}</div>
                      <TipRow k="Koszt 36 dok.">{usd(m.cost_usd?.train)}</TipRow>
                      <TipRow k="Parametry">{pb(m.params_b)}</TipRow>
                      <TipRow k="F1 trening">{f1s(m.f1.train) ?? "—"}</TipRow>
                    </>
                  )}
                />
              }
            />
            <Bar dataKey="cost" radius={4} minPointSize={3} isAnimationActive={false}>
              {rows.map((r) => (
                <Cell key={r.m.id} fill={`var(--color-${r.key})`} />
              ))}
              <LabelList dataKey="tag" content={RightLabel} />
            </Bar>
          </BarChart>
        </ChartContainer>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {(Object.keys(config) as (keyof typeof config)[]).map((k) => (
            <LegendDot key={k} color={config[k].color}>
              {config[k].label}
            </LegendDot>
          ))}
          {unmeasured.length > 0 && <span>Bez pomiaru kosztu: {unmeasured.map((m) => m.name).join(", ")}</span>}
        </div>
      </CardContent>
    </Card>
  )
}
