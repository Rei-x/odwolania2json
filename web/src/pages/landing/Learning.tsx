import type { ReactNode } from "react"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, type ChartConfig } from "@/components/ui/chart"
import { prefersReducedMotion, useInViewOnce } from "./hooks"
import { Reveal, SectionHead } from "./Reveal"

// Illustrative curve only (the card says "schemat"), so no tooltip or numeric axis.
const CURVE = [0.18, 0.31, 0.43, 0.52, 0.6, 0.66, 0.71, 0.75, 0.78, 0.8, 0.81].map((y, i) => ({ i, y }))
const config = { y: { label: "Trafność", color: "var(--primary)" } } satisfies ChartConfig

function LearningChart() {
  return (
    <ChartContainer config={config} className="aspect-auto h-[220px] w-full">
      <AreaChart data={CURVE} margin={{ left: 0, right: 4, top: 8, bottom: 0 }}>
        <defs>
          <linearGradient id="lp-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="var(--color-y)" stopOpacity={0.28} />
            <stop offset="95%" stopColor="var(--color-y)" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="i" hide />
        <YAxis domain={[0, 1]} hide />
        <Area
          dataKey="y" type="natural" stroke="var(--color-y)" strokeWidth={2.5} fill="url(#lp-fill)"
          isAnimationActive={!prefersReducedMotion()} animationDuration={1800} animationEasing="ease-out"
        />
      </AreaChart>
    </ChartContainer>
  )
}

function LoopSvg() {
  const rm = prefersReducedMotion()
  const node = (x: number, y: number, c: string, label: string, sub: string | null, below: boolean, icon: ReactNode) => (
    <g className="nd" transform={`translate(${x} ${y})`}>
      <circle r="34" className="bg" style={{ stroke: c }} strokeWidth="2" />
      <circle r="34" style={{ fill: c }} opacity=".08" />
      <g fill="none" style={{ stroke: c }} strokeWidth="2.4" strokeLinejoin="round" strokeLinecap="round">{icon}</g>
      <text y={below ? 58 : -50} textAnchor="middle">{label}</text>
      {sub && <text className="s" y={76} textAnchor="middle">{sub}</text>}
    </g>
  )
  return (
    <svg viewBox="0 0 440 400" role="img" aria-label="Pętla uczenia: poprawka, pamięć, few-shot">
      <defs>
        <linearGradient id="lp-lg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" style={{ stopColor: "var(--primary)" }} />
          <stop offset=".5" style={{ stopColor: "var(--chart-3)" }} />
          <stop offset="1" style={{ stopColor: "var(--sage)" }} />
        </linearGradient>
      </defs>
      <circle cx="220" cy="200" r="130" fill="none" style={{ stroke: "var(--muted)" }} strokeWidth="2" />
      <circle cx="220" cy="200" r="130" fill="none" stroke="url(#lp-lg)" strokeWidth="3" strokeLinecap="round" strokeDasharray="120 697" transform="rotate(-90 220 200)">
        {!rm && <animate attributeName="stroke-dashoffset" from="817" to="0" dur="6s" repeatCount="indefinite" />}
      </circle>
      {node(220, 70, "var(--primary)", "Poprawiasz pole", null, false, <path d="M-11 9l3-10 13-13 7 7-13 13zM-8 -1l7 7" />)}
      {node(333, 265, "var(--chart-3)", "Pamięć", "zweryfikowane przykłady", true,
        <><ellipse cx="0" cy="-9" rx="13" ry="5" /><path d="M-13 -9v18c0 2.8 5.8 5 13 5s13-2.2 13-5V-9M-13 0c0 2.8 5.8 5 13 5s13-2.2 13-5" /></>)}
      {node(107, 265, "var(--sage)", "Few-shot", "dla podobnych", true,
        <><rect x="-14" y="-12" width="17" height="22" rx="3" /><rect x="-3" y="-6" width="17" height="22" rx="3" className="bg" /></>)}
      <g transform="translate(220 182)" textAnchor="middle">
        <text y="-4" className="center1">/api/feedback</text>
        <text y="20" className="center2">przycisk „Zatwierdź”</text>
      </g>
    </svg>
  )
}

export function Learning() {
  const [ref, seen] = useInViewOnce<HTMLDivElement>({ threshold: 0.4 })
  return (
    <section className="sec" id="uczenie">
      <div className="wrap">
        <SectionHead title="Każda poprawka zostaje w pamięci.">
          <p className="lede">Zatwierdzony dokument staje się przykładem few-shot dla podobnych.</p>
        </SectionHead>
        <div className="learn">
          <Reveal>
            <Card className="lp-card loop h-full">
              <CardContent className="grid h-full place-items-center"><LoopSvg /></CardContent>
            </Card>
          </Reveal>
          <Reveal delay={1}>
            <Card className="lp-card h-full">
              <CardHeader>
                <CardTitle className="text-lg font-semibold">Trafność rośnie z każdym zatwierdzeniem</CardTitle>
                <CardDescription>Schemat poglądowy</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-1 flex-col">
                <div ref={ref} className="h-[220px]">{seen && <LearningChart />}</div>
                <div className="mt-2 flex justify-between font-mono text-xs text-muted-foreground">
                  <span>pierwsze dokumenty</span><span>zatwierdzone →</span>
                </div>
                <p className="mt-auto flex items-center gap-2 pt-6 text-sm text-muted-foreground">
                  <span className="size-2 shrink-0 rounded-full bg-success" />
                  Nowe reguły zawsze przechodzą przegląd człowieka.
                </p>
              </CardContent>
            </Card>
          </Reveal>
        </div>
      </div>
    </section>
  )
}
