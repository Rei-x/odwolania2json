import { Bar, BarChart, CartesianGrid, Cell, LabelList, XAxis, YAxis } from "recharts"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { LogoTick, PointTip, RightLabel, TipRow, useWide } from "./chart-kit"
import { f1s, fmt, pb, pct, usd } from "./lib"
import { Dash } from "./parts"
import type { Benchmarks, OcrModel } from "./types"

const config = {
  f1: { label: "F1", color: "var(--chart-4)" },
  chosen: { label: "Ministral 8B (profil Auto)", color: "var(--primary)" },
} satisfies ChartConfig

type Row = { name: string; f1: number; tag: string; m: OcrModel }

export function OcrSection({ ocr }: { ocr: Benchmarks["ocr"] }) {
  const wide = useWide(640)
  const rows: Row[] = ocr.models
    .filter((m) => m.f1 != null)
    .sort((a, b) => b.f1! - a.f1!)
    .map((m) => ({ name: m.name, f1: m.f1!, tag: f1s(m.f1)!, m }))
  const ids = Object.fromEntries(rows.map((r) => [r.name, r.m.id]))
  const missing = ocr.models.filter((m) => m.f1 == null)
  return (
    <div className="grid gap-4 lg:grid-cols-[1.25fr_1fr]">
      <Card>
        <CardHeader>
          <CardTitle>F1 po OCR + ekstrakcji</CardTitle>
          <CardDescription>Oś od 0,95.</CardDescription>
        </CardHeader>
        <CardContent>
          <ChartContainer config={config} className="aspect-auto w-full" style={{ height: rows.length * 38 + 30 }}>
            <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 64, bottom: 0, left: 0 }} barCategoryGap={9}>
              <CartesianGrid horizontal={false} />
              <XAxis type="number" domain={[0.95, 1]} ticks={wide ? [0.95, 0.96, 0.97, 0.98, 0.99, 1] : [0.95, 0.97, 0.99, 1]} tickFormatter={(v: number) => fmt(v, 2)!} tickLine={false} axisLine={false} allowDataOverflow />
              <YAxis type="category" dataKey="name" width={wide ? 170 : 132} tickLine={false} axisLine={false} interval={0} tick={<LogoTick ids={ids} fontSize={wide ? 12.5 : 11} />} />
              <ChartTooltip
                cursor={{ fill: "var(--muted)", opacity: 0.6 }}
                content={
                  <PointTip<Row>
                    render={({ m }) => (
                      <>
                        <div className="font-medium">{m.name}</div>
                        <TipRow k="F1">{f1s(m.f1)}</TipRow>
                        {m.params_b != null && <TipRow k="Parametry">{pb(m.params_b)}</TipRow>}
                        <TipRow k="Koszt">{usd(m.cost_usd) ?? "—"}</TipRow>
                        {m.note && <div className="max-w-60 text-muted-foreground">{m.note}</div>}
                      </>
                    )}
                  />
                }
              />
              <Bar dataKey="f1" radius={4} isAnimationActive={false}>
                {rows.map((r) => (
                  <Cell key={r.m.id} fill={r.m.id.includes("ministral-8b") ? "var(--color-chosen)" : "var(--color-f1)"} />
                ))}
                <LabelList dataKey="tag" content={RightLabel} />
              </Bar>
            </BarChart>
          </ChartContainer>
          {missing.length > 0 && (
            <ul className="mt-3 space-y-0.5 text-xs text-muted-foreground">
              {missing.map((m) => (
                <li key={m.id}>
                  <span className="font-medium text-foreground">{m.name}</span>: {m.placeholder ? "w trakcie pomiaru" : m.note || m.status || "brak wyniku"}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Lokalny OCR a VLM przez API</CardTitle>
          <CardDescription>Mniej znaczy lepiej.</CardDescription>
        </CardHeader>
        <CardContent className="px-2 sm:px-4">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="text-xs text-muted-foreground">Silnik</TableHead>
                <TableHead className="text-right text-xs text-muted-foreground">CER</TableHead>
                <TableHead className="text-right text-xs text-muted-foreground">s / strona</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ocr.local.map((l) => (
                <TableRow key={l.name}>
                  <TableCell className="whitespace-normal">
                    <div className="font-medium">{l.name}</div>
                    <div className="text-xs text-muted-foreground">{l.note ?? l.where}</div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{l.cer != null ? pct(l.cer) : <Dash />}</TableCell>
                  <TableCell className="text-right tabular-nums">{l.sec_per_page ?? <Dash />}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="mt-3 px-2 text-xs text-muted-foreground">Lokalny OCR działa offline, ale na CPU jest wolniejszy i myli się częściej. Domyślnie OCR robi mały model wizyjny przez API.</p>
        </CardContent>
      </Card>
    </div>
  )
}
