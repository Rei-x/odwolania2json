import { Link } from "react-router-dom"
import { Bar, BarChart, CartesianGrid, LabelList, XAxis, YAxis } from "recharts"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig,
} from "@/components/ui/chart"
import { useInViewOnce } from "./hooks"
import { ArrowIcon, CheckIcon, Reveal, SectionHead } from "./Reveal"
import { logoFor } from "@/components/brand/model-logo"
import type { Vendor } from "./VendorLogo"

function vendorPath(vendor: Vendor) {
  const l = logoFor(vendor === "mistral" ? "mistralai/ministral" : "anthropic/claude")
  return l && "path" in l ? { d: l.path, color: l.color } : null
}

/* Numbers from docs/bench_parsers.md (same train subset and blind set for all three setups). */
const FLOOR = 0.9
type Row = { id: string; short?: string; line1: string; line2: string; vendor: Vendor; train: number; blind: number; cost: string }
const ROWS: Row[] = [
  { id: "opus", line1: "Claude Opus 5.5", line2: "referencja", short: "Opus 5.5", vendor: "anthropic", train: 1, blind: 1, cost: "$2,94" },
  { id: "ours", line1: "Ministral 8B", line2: "+ Wróbelek", vendor: "mistral", train: 0.997, blind: 0.985, cost: "$0,11" },
  { id: "plain", line1: "Ministral 8B", line2: "jeden prompt", vendor: "mistral", train: 0.956, blind: 0.933, cost: "$0,03" },
]
const BY_ID = Object.fromEntries(ROWS.map((r) => [r.id, r]))

const config = {
  train: { label: "dane UZP", color: "var(--sage)" },
  blind: { label: "ślepy zbiór", color: "var(--primary)" },
} satisfies ChartConfig

const f3 = (n: number) => n.toFixed(3).replace(".", ",")

/** Category tick: vendor mark above a two-line model label. */
function ModelTick({ x = 0, y = 0, payload, narrow }: { x?: number; y?: number; payload?: { value: string }; narrow?: boolean }) {
  const r = BY_ID[payload?.value ?? ""]
  if (!r) return null
  const v = vendorPath(r.vendor)
  return (
    <g transform={`translate(${x},${y + 6})`}>
      {v && <g transform="translate(-8,0) scale(0.667)" style={{ fill: v.color ?? "var(--foreground)" }}><path d={v.d} /></g>}
      <text y={30} textAnchor="middle" className="fill-foreground" fontSize={12} fontWeight={600}>{narrow && r.short ? r.short : r.line1}</text>
      <text y={46} textAnchor="middle" className="fill-muted-foreground" fontSize={12}>{r.line2}</text>
    </g>
  )
}

function ResultsChart() {
  const narrow = typeof window !== "undefined" && window.innerWidth < 640
  const data = ROWS.map((r) => ({ ...r, trainR: [FLOOR, r.train], blindR: [FLOOR, r.blind], trainL: f3(r.train), blindL: f3(r.blind) }))
  return (
    <ChartContainer config={config} className="aspect-auto h-[320px] w-full">
      <BarChart data={data} margin={{ left: 0, right: 0, top: 22, bottom: 8 }} barGap={narrow ? 10 : 4} barCategoryGap="22%">
        <CartesianGrid vertical={false} />
        <XAxis dataKey="id" tickLine={false} axisLine={false} interval={0} height={60} tick={<ModelTick narrow={narrow} />} />
        <YAxis domain={[FLOOR, 1]} ticks={[0.9, 0.95, 1]} tickFormatter={(n: number) => n.toFixed(2).replace(".", ",")} tickLine={false} axisLine={false} width={36} />
        <ChartTooltip
          cursor={false}
          content={
            <ChartTooltipContent
              labelFormatter={(_l, p) => {
                const r = p?.[0]?.payload as Row | undefined
                return r ? `${r.line1} ${r.line2} · koszt obu zbiorów ${r.cost}` : ""
              }}
              formatter={(_v, name, item) => {
                const r = item.payload as Row
                const key = String(name).startsWith("train") ? "train" : "blind"
                return (
                  <div className="flex w-full items-center justify-between gap-4">
                    <span className="flex items-center gap-1.5 text-muted-foreground">
                      <span className="size-2.5 rounded-[2px]" style={{ background: `var(--color-${key})` }} />
                      F1, {config[key].label}
                    </span>
                    <span className="font-mono font-medium tabular-nums">{f3(r[key])}</span>
                  </div>
                )
              }}
            />
          }
        />
        <ChartLegend content={<ChartLegendContent nameKey="value" className="pt-2" />} verticalAlign="bottom" />
        <Bar dataKey="trainR" name="train" fill="var(--color-train)" radius={6} maxBarSize={64} animationDuration={1100}>
          <LabelList dataKey="trainL" position="top" className="fill-foreground" fontSize={narrow ? 10 : 11} fontWeight={600} />
        </Bar>
        <Bar dataKey="blindR" name="blind" fill="var(--color-blind)" radius={6} maxBarSize={64} animationDuration={1100}>
          <LabelList dataKey="blindL" position="top" className="fill-foreground" fontSize={narrow ? 10 : 11} fontWeight={600} />
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
        <SectionHead title="Mały model z pipeline'em ≈ Opus.">
          <p className="lede">Ten sam Ministral 8B: z Wróbelkiem 0,985 F1 na ślepym zbiorze, z jednym promptem 0,933. Około 27 razy taniej niż Opus.</p>
        </SectionHead>
        <Reveal>
          <Card className="lp-card">
            <CardHeader>
              <CardTitle className="text-lg font-semibold">F1 na danych UZP i na ślepym zbiorze</CardTitle>
              <CardDescription>Skala 0,90–1,00. Koszt przebiegu obu zbiorów: Opus $2,94, Wróbelek $0,11.</CardDescription>
            </CardHeader>
            <CardContent>
              <div ref={ref} className="h-[320px]">{seen && <ResultsChart />}</div>
            </CardContent>
          </Card>
        </Reveal>
        <Reveal className="corpus">
          <b>Zebraliśmy prawdziwe akta z internetu: 929 PDF-ów ze 111 źródeł.</b>
          <span>Na 487 sprawdzonych dokumentach zgodność pól wynosi około 95%.</span>
        </Reveal>
        <Reveal className="mt-5 flex flex-wrap items-center gap-2">
          {["mediana 2,7 s / dokument", "modele 3–8B w UE", "bez GPU", "na własnym serwerze", "open source"].map((c) => (
            <Badge key={c} variant="outline" className="h-8 gap-1.5 bg-card px-3 text-sm [&>svg]:size-3.5! [&>svg]:text-sage">
              <CheckIcon />{c}
            </Badge>
          ))}
          <Button nativeButton={false} variant="link" render={<Link to="/benchmarks" />} className="ml-auto h-8 px-0 text-sm">
            Wszystkie benchmarki <ArrowIcon />
          </Button>
        </Reveal>
      </div>
    </section>
  )
}
