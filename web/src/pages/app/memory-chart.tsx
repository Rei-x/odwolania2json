import { Area, AreaChart, XAxis, YAxis } from "recharts"
import { type ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
import { fmtPct } from "@/lib/format"

const config = {
  acc: { label: "Trafność", color: "var(--primary)" },
} satisfies ChartConfig

/** Cumulative share of fields accepted without correction, review after review (downsampled to ≤ 60 samples). */
export function MemoryChart({ timeline }: { timeline: { cumulative_accuracy: number }[] }) {
  const step = Math.max(1, Math.ceil(timeline.length / 60))
  const data = timeline
    .filter((_, i) => i % step === 0 || i === timeline.length - 1)
    .map((t, i) => ({ n: Math.min(timeline.length, i * step + 1), acc: +(t.cumulative_accuracy * 100).toFixed(1) }))
  const min = Math.max(0, Math.floor(Math.min(...data.map((d) => d.acc)) / 5) * 5 - 5)
  return (
    <ChartContainer config={config} className="aspect-auto h-24 w-full">
      <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
        <defs>
          <linearGradient id="mem-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-acc)" stopOpacity={0.3} />
            <stop offset="100%" stopColor="var(--color-acc)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis dataKey="n" hide />
        <YAxis domain={[min, 100]} hide />
        <ChartTooltip
          cursor={false}
          content={<ChartTooltipContent labelFormatter={(_, p) => `Recenzja ${p?.[0]?.payload?.n ?? ""}`} formatter={(v) => (
            <span className="flex w-full justify-between gap-3"><span className="text-muted-foreground">Trafność</span><b className="tabular-nums">{fmtPct(Number(v) / 100)}</b></span>
          )} />}
        />
        <Area dataKey="acc" type="monotone" stroke="var(--color-acc)" strokeWidth={2} fill="url(#mem-fill)" isAnimationActive={false} />
      </AreaChart>
    </ChartContainer>
  )
}
