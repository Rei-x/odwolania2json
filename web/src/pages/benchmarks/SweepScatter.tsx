import { CartesianGrid, LabelList, Scatter, ScatterChart, XAxis, YAxis, ZAxis } from "recharts"
import { ModelName } from "@/components/brand/model-logo"
import { Card, CardContent } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart"
import { LegendDot, logoLabel, PointTip, smallArea, TipRow, useWide } from "./chart-kit"
import { f1s, fmt, logTicks, pb, PD_LABEL, secs, usd } from "./lib"
import type { SweepRun } from "./types"

const config = {
  pareto: { label: "Najlepszy przy swoim rozmiarze", color: "var(--primary)" },
  eu: { label: "Hosting w UE", color: "var(--sage)" },
  noeu: { label: "Poza UE", color: "var(--chart-3)" },
} satisfies ChartConfig

type Pt = { x: number; y: number; z: number; r: SweepRun; id: string; name: string; label: string }

export function SweepTipBody({ r }: { r: SweepRun }) {
  const pd = r.blind?.per_doc ?? {}
  return (
    <>
      <div className="font-medium">
        <ModelName id={r.model} name={r.label} />
      </div>
      <TipRow k="Parametry">{pb(r.params_b)}</TipRow>
      <TipRow k="Hosting">{r.eu ? "UE: " + r.eu_providers!.join(", ") : "poza UE"}</TipRow>
      <TipRow k="F1 ślepy">{f1s(r.fb) ?? "brak"}</TipRow>
      <TipRow k="F1 trening">{f1s(r.ft) ?? "brak"}</TipRow>
      {Object.entries(pd).map(([k, v]) => (
        <TipRow key={k} k={<span className="pl-2">{PD_LABEL[k] || k}</span>}>
          {f1s(v) ?? "—"}
        </TipRow>
      ))}
      <TipRow k="Koszt · czas">
        {usd(r.cost) ?? "—"} · {secs(r.sec) ?? "—"}
      </TipRow>
      {r.blind?.negatives_ok && <TipRow k="Negatywy odrzucone">{r.blind.negatives_ok}</TipRow>}
    </>
  )
}

/** Blind F1 vs size (log); bubble area = cost; colour = best-at-its-size / EU hosting. */
export function SweepScatter({ runs }: { runs: SweepRun[] }) {
  const wide = useWide()
  const plotted = runs.filter((r) => r.fb != null && r.params_b != null && r.params_b > 0)
  const off = runs.filter((r) => !plotted.includes(r))
  if (!plotted.length)
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">Wykres pojawi się po pierwszym udanym przebiegu na ślepym zbiorze.</CardContent>
      </Card>
    )
  const maxB = Math.max(...plotted.map((r) => r.params_b!))
  const LO = 1, HI = Math.max(100, maxB * 3)
  const fmin = Math.min(...plotted.map((r) => r.fb!))
  const ymin = Math.max(0, Math.floor((fmin - 0.02) * 20) / 20)
  const step = 1 - ymin > 0.2 ? 0.1 : 0.05
  const yticks: number[] = []
  for (let f = ymin; f <= 1.0001; f += step) yticks.push(+f.toFixed(2))
  const pts: Pt[] = plotted.map((r) => ({ x: r.params_b!, y: r.fb!, z: r.cost ?? 0, r, id: r.model, name: r.label, label: plotted.length <= 14 || r.pareto ? r.label : "" }))
  // dots that sit on top of each other share one label
  const yTol = (1 - ymin) * 0.035
  const heads: Pt[] = []
  for (const p of [...pts].sort((a, b) => b.y - a.y)) {
    if (!p.label) continue
    const h = heads.find((h) => Math.abs(Math.log10(h.x) - Math.log10(p.x)) < 0.12 && Math.abs(h.y - p.y) < yTol)
    if (h) {
      h.label += " · " + p.label
      p.label = ""
    } else heads.push(p)
  }
  const keys = Object.keys(config) as (keyof typeof config)[]
  const of = (k: keyof typeof config) => pts.filter((p) => (k === "pareto" ? p.r.pareto : !p.r.pareto && (k === "eu") === p.r.eu))
  const frontier = pts.filter((p) => p.r.pareto).sort((a, b) => a.x - b.x)
  return (
    <Card>
      <CardContent>
        <ChartContainer config={config} className="aspect-auto h-[300px] w-full sm:h-[380px]">
          <ScatterChart margin={{ top: 24, right: wide ? 40 : 8, bottom: 8, left: 0 }}>
            {smallArea(LO, wide)}
            <CartesianGrid vertical={false} />
            <XAxis type="number" dataKey="x" scale="log" domain={[LO, HI]} ticks={logTicks(LO, HI)} tickFormatter={(v: number) => pb(v)} tickLine={false} axisLine={false} allowDataOverflow />
            <YAxis type="number" dataKey="y" domain={[ymin, 1]} ticks={yticks} tickFormatter={(v: number) => fmt(v, 2)!} tickLine={false} axisLine={false} width={44} />
            <ZAxis type="number" dataKey="z" range={[70, 520]} />
            <ChartTooltip cursor={false} content={<PointTip<Pt> render={({ r }) => <SweepTipBody r={r} />} />} />
            {frontier.length > 1 && <Scatter data={frontier} line={{ stroke: "var(--primary)", strokeDasharray: "5 4", strokeWidth: 1.5 }} shape={() => <g />} legendType="none" isAnimationActive={false} />}
            {keys.map((k) => {
              const data = of(k)
              return (
                <Scatter key={k} data={data} fill={`var(--color-${k})`} fillOpacity={0.85} stroke="var(--card)" strokeWidth={1.5} isAnimationActive={false}>
                  {wide && <LabelList dataKey="label" content={logoLabel(data, (d) => d.label, "right")} />}
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
          <span>Wielkość kółka: koszt przebiegu</span>
          {off.length > 0 && <span>Bez wyniku: {off.map((r) => r.label).join(", ")}</span>}
        </div>
      </CardContent>
    </Card>
  )
}
