import { useState, type ReactNode } from "react"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { errorOf, f1s, negRatio, pb, PD_LABEL, secs, usd } from "./lib"
import { cmp, Dash, EuBadge, HintBadge, NoResult, PointsPill, SortHead, useSort } from "./parts"
import type { SweepRun } from "./types"

type Part = "blind" | "train"

/** Cell value with a hover breakdown (train + blind). */
function Split({ value, hint }: { value: ReactNode; hint: string }) {
  return (
    <Tooltip>
      <TooltipTrigger render={<span />} className="cursor-help">
        {value}
      </TooltipTrigger>
      <TooltipContent>{hint}</TooltipContent>
    </Tooltip>
  )
}

export function SweepTable({ runs, seen }: { runs: SweepRun[]; seen: Set<string> | null }) {
  const [key, setKey] = useState("blind")
  const [dir, setDir] = useState<1 | -1>(-1)
  const [part, setPart] = useState<Part>("blind")
  const sort = useSort(key, setKey, dir, setDir, (k) => (["name", "params", "cost", "time"].includes(k) ? 1 : -1))
  const order = Object.keys(PD_LABEL)
  const pdKeys = [...new Set(runs.flatMap((r) => Object.keys(r[part]?.per_doc ?? {})))].sort(
    (a, b) => (order.indexOf(a) + 1 || 99) - (order.indexOf(b) + 1 || 99),
  )
  const cols: { k: string; label: string; get: (r: SweepRun) => number | string; num?: boolean; title?: string }[] = [
    { k: "name", label: "Model", get: (r) => r.label.toLowerCase() },
    { k: "params", label: "Parametry", get: (r) => r.params_b ?? 1e9, num: true },
    { k: "pts", label: "Punkty", get: (r) => r.pts ?? -1, num: true },
    { k: "blind", label: "F1 ślepy", get: (r) => r.fb ?? -1, num: true },
    { k: "train", label: "F1 trening", get: (r) => r.ft ?? -1, num: true },
    ...pdKeys.map((k) => ({
      k: "pd:" + k,
      label: PD_LABEL[k] || k,
      get: (r: SweepRun) => r[part]?.per_doc?.[k] ?? -1,
      num: true,
      title: `F1 dla typu dokumentu (${part === "blind" ? "ślepy zbiór" : "trening"})`,
    })),
    { k: "neg", label: "Negatywy", get: (r) => negRatio(r.blind?.negatives_ok)?.r ?? -1, num: true },
    { k: "cost", label: "Koszt", get: (r) => r.cost ?? 1e9, num: true },
    { k: "time", label: "Czas", get: (r) => r.sec ?? 1e9, num: true },
  ]
  const active = cols.find((c) => c.k === key) ?? cols[3]
  const rows = [...runs].sort((a, b) => cmp(active.get(a), active.get(b)) * dir || (b.fb ?? -1) - (a.fb ?? -1))
  return (
    <Card>
      <CardHeader>
        <CardTitle>Ranking sweepu</CardTitle>
        <CardAction className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="hidden sm:inline">F1 per typ dokumentu:</span>
          <Tabs value={part} onValueChange={(v) => setPart(v as Part)}>
            <TabsList className="h-7">
              <TabsTrigger value="blind" className="px-2.5 text-xs">
                ślepy
              </TabsTrigger>
              <TabsTrigger value="train" className="px-2.5 text-xs">
                trening
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </CardAction>
      </CardHeader>
      <CardContent className="px-2 sm:px-4">
        <Table className="text-[13px]">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              {cols.map((c) => (
                <TableHead key={c.k} className={cn("px-1.5", c.num && "text-right", c.k.startsWith("pd:") && "bg-muted/40")}>
                  <SortHead label={c.label} active={active.k === c.k} dir={dir} onClick={() => sort(c.k)} align={c.num ? "right" : "left"} title={c.title} />
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => {
              const p = r[part]
              const isNew = seen != null && !seen.has(r.model)
              return (
                <TableRow
                  key={r.model}
                  className={cn(isNew && "animate-in bg-wheat/20 duration-700 fade-in slide-in-from-left-2")}
                >
                  <TableCell className="min-w-52 px-1.5 py-2 whitespace-normal">
                    <div className="flex flex-wrap items-center gap-1">
                      <span className="mr-0.5 font-medium">{r.label}</span>
                      <EuBadge eu={r.eu_providers ?? []} providers={r.providers} />
                      {r.pareto && (
                        <HintBadge hint="Nikt nie ma wyższego F1 ślepego przy tej samej lub wyższej liczbie punktów" className="bg-primary text-primary-foreground">
                          Pareto
                        </HintBadge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="px-1.5 text-right tabular-nums">{r.params_b == null ? <Dash>nieznane</Dash> : pb(r.params_b)}</TableCell>
                  <TableCell className="px-1.5 text-right">
                    <PointsPill p={r.pts} />
                  </TableCell>
                  <TableCell className="px-1.5 text-right font-bold tabular-nums">{f1s(r.fb) ?? <NoResult error={errorOf(r, "blind")} />}</TableCell>
                  <TableCell className="px-1.5 text-right tabular-nums">{f1s(r.ft) ?? <NoResult error={errorOf(r, "train")} />}</TableCell>
                  {pdKeys.map((k) => {
                    const v = p?.per_doc?.[k]
                    return (
                      <TableCell key={k} className={cn("bg-muted/25 px-1.5 text-right text-xs tabular-nums", v != null && v < 0.9 && "text-chart-3")}>
                        {f1s(v) ?? (p?.f1 == null ? <NoResult error={errorOf(r, part)}>—</NoResult> : <Dash />)}
                      </TableCell>
                    )
                  })}
                  <TableCell className={cn("px-1.5 text-right tabular-nums", (negRatio(r.blind?.negatives_ok)?.r ?? 1) < 1 && "font-semibold text-chart-3")}>
                    {r.blind?.negatives_ok ?? <NoResult error={errorOf(r, "blind")}>—</NoResult>}
                  </TableCell>
                  <TableCell className="px-1.5 text-right tabular-nums">
                    {usd(r.cost) != null ? (
                      <Split value={usd(r.cost)} hint={`trening ${usd(r.train?.cost) ?? "—"} + ślepy ${usd(r.blind?.cost) ?? "—"}`} />
                    ) : (
                      <NoResult error={errorOf(r, "blind") || errorOf(r, "train")}>—</NoResult>
                    )}
                  </TableCell>
                  <TableCell className="px-1.5 text-right tabular-nums">
                    {secs(r.sec) != null ? <Split value={secs(r.sec)} hint={`trening ${secs(r.train?.seconds) ?? "—"} + ślepy ${secs(r.blind?.seconds) ?? "—"}`} /> : <Dash />}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
        <p className="mt-3 px-2 text-xs text-muted-foreground">
          Koszt i czas: trening + ślepy zbiór. Negatywy: odrzucone dokumenty spoza zakresu. Najedź na „brak wyniku”, aby zobaczyć błąd.
        </p>
      </CardContent>
    </Card>
  )
}
