import { Link } from "react-router-dom"
import { Bar, BarChart, CartesianGrid, Cell, LabelList, XAxis, YAxis } from "recharts"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { useInViewOnce } from "./hooks"
import { ArrowIcon, CheckIcon, Reveal, SectionHead } from "./Reveal"

// Axis runs 0.90 → 1.00, so every bar is a range starting at the axis floor.
const FLOOR = 0.9
type Row = { name: string; desc: string; range: [number, number]; v: string; key: "f1" | "cls" }
const ROWS: Row[] = [
  { name: "Dane UZP", desc: "60 spraw + 16 spoza zakresu", range: [FLOOR, 1], v: "1,000", key: "f1" },
  { name: "Ślepy zbiór", desc: "20 nowych spraw, zamrożony", range: [FLOOR, 0.999], v: "0,999", key: "f1" },
  { name: "Trudne warianty", desc: "konsorcja, JDG, odmiana nazwisk", range: [FLOOR, 0.999], v: "0,999", key: "f1" },
  { name: "Skany UZP", desc: "bez warstwy tekstowej", range: [FLOOR, 1], v: "1,000", key: "f1" },
  { name: "Zdegradowane", desc: "szum, obrót, pieczęcie, zdjęcie", range: [0.97, 1], v: "0,97–1,00", key: "f1" },
  { name: "487 dok. KIO", desc: "zgodność z Claude Opus jako anotatorem", range: [FLOOR, 0.95], v: "~0,95", key: "f1" },
  { name: "Klasyfikacja", desc: "trafność, 116 trudnych przypadków", range: [FLOOR, 0.983], v: "98,3%", key: "cls" },
]

const config = {
  f1: { label: "F1", color: "var(--sage)" },
  cls: { label: "Trafność", color: "var(--primary)" },
} satisfies ChartConfig

const comma = (n: number) => n.toFixed(2).replace(".", ",")

function ResultsChart() {
  return (
    <ChartContainer config={config} className="aspect-auto h-[340px] w-full">
      <BarChart data={ROWS} layout="vertical" margin={{ left: 4, right: 76, top: 4, bottom: 4 }} barCategoryGap={10}>
        <CartesianGrid horizontal={false} />
        <XAxis type="number" domain={[FLOOR, 1]} ticks={[0.9, 0.95, 1]} tickFormatter={comma} tickLine={false} axisLine={false} />
        <YAxis type="category" dataKey="name" width={104} tickLine={false} axisLine={false} tick={{ fontSize: 12 }} />
        <ChartTooltip
          cursor={false}
          content={
            <ChartTooltipContent
              formatter={(_v, _n, item) => {
                const r = item.payload as Row
                return (
                  <div className="flex w-full items-center justify-between gap-4">
                    <span className="text-muted-foreground">{r.desc}</span>
                    <span className="font-mono font-medium tabular-nums">{r.v}</span>
                  </div>
                )
              }}
            />
          }
        />
        <Bar dataKey="range" radius={6} barSize={20} animationDuration={1200}>
          {ROWS.map((r) => <Cell key={r.name} fill={`var(--color-${r.key})`} />)}
          <LabelList dataKey="v" position="right" offset={10} className="fill-foreground font-semibold" fontSize={13} />
        </Bar>
      </BarChart>
    </ChartContainer>
  )
}

export function Results() {
  // mount the chart on first view so the bars grow in as it scrolls into sight
  const [ref, seen] = useInViewOnce<HTMLDivElement>({ threshold: 0.3 })
  return (
    <section className="sec" id="wyniki">
      <div className="wrap">
        <SectionHead eyebrow="Wyniki" title="Zmierzone, nie obiecane." />
        <Reveal>
          <Card className="lp-card">
            <CardHeader>
              <CardTitle className="text-lg font-semibold">Jakość na zbiorach testowych</CardTitle>
              <CardDescription>F1, zgodność i trafność w skali 0,90–1,00.</CardDescription>
            </CardHeader>
            <CardContent>
              <div ref={ref} className="h-[340px]">{seen && <ResultsChart />}</div>
            </CardContent>
          </Card>
        </Reveal>
        <Reveal className="mt-6 flex flex-wrap items-center gap-2">
          {["707 testów + CI", "open-source", "tylko CPU", "open-weight w UE"].map((c) => (
            <Badge key={c} variant="outline" className="h-8 gap-1.5 bg-card px-3 text-sm [&>svg]:size-3.5! [&>svg]:text-sage">
              <CheckIcon />{c}
            </Badge>
          ))}
          <Button nativeButton={false} variant="link" render={<Link to="/benchmarks" />} className="ml-auto h-8 px-0 text-sm">
            Benchmarki modeli <ArrowIcon />
          </Button>
        </Reveal>
      </div>
    </section>
  )
}
