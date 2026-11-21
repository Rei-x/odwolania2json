import { useState } from "react"
import { Info } from "lucide-react"
import { ModelName } from "@/components/brand/model-logo"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { ARCH_LABEL, f1s, pb, usd } from "./lib"
import { cmp, Dash, Pending, SortHead, useSort } from "./parts"
import type { BenchModel } from "./types"

type Key = "name" | "params" | "train" | "blind" | "cost"

export function ModelsTable({ models }: { models: BenchModel[] }) {
  const [key, setKey] = useState<Key>("params")
  const [dir, setDir] = useState<1 | -1>(1)
  const sort = useSort(key, setKey, dir, setDir)
  const cols: { k: Key; label: string; get: (m: BenchModel) => number | string; num?: boolean }[] = [
    { k: "name", label: "Model", get: (m) => m.name.toLowerCase() },
    { k: "params", label: "Parametry", get: (m) => m.params_b ?? 1e9, num: true },
    { k: "train", label: "F1 trening", get: (m) => m.f1.train ?? -1, num: true },
    { k: "blind", label: "F1 ślepy", get: (m) => m.f1.blind ?? -1, num: true },
    { k: "cost", label: "Koszt 36 dok.", get: (m) => m.cost_usd?.train ?? 1e9, num: true },
  ]
  const get = cols.find((c) => c.k === key)!.get
  const rows = [...models].sort((a, b) => cmp(get(a), get(b)) * dir)
  const missing = (m: BenchModel) => (m.placeholder ? <Pending /> : <Dash />)
  return (
    <Card>
      <CardContent className="px-2 sm:px-4">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              {cols.map((c) => (
                <TableHead key={c.k} className={cn("px-3", c.num && "text-right")}>
                  <SortHead label={c.label} active={key === c.k} dir={dir} onClick={() => sort(c.k)} align={c.num ? "right" : "left"} />
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((m) => (
              <TableRow key={m.id} className={cn(m.chosen && "bg-accent/50 hover:bg-accent/70")}>
                <TableCell className="px-3 py-2.5">
                  <div className="flex items-center gap-1.5">
                    <ModelName id={m.id} name={m.name} className="font-medium" />
                    {m.chosen && <Badge>wybrany</Badge>}
                    {m.note && (
                      <Tooltip>
                        <TooltipTrigger render={<span />} className="cursor-help text-muted-foreground hover:text-foreground" aria-label="Uwagi">
                          <Info className="size-3.5" />
                        </TooltipTrigger>
                        <TooltipContent className="max-w-xs">{m.note}</TooltipContent>
                      </Tooltip>
                    )}
                  </div>
                  {m.arch && m.arch !== "dense" && <div className="text-xs text-muted-foreground">{ARCH_LABEL[m.arch]}</div>}
                </TableCell>
                <TableCell className="px-3 text-right tabular-nums">
                  {m.params_b == null ? <Dash>nieznane</Dash> : m.params_b === 0 ? "bez LLM" : pb(m.params_b)}
                  {m.active_b != null && m.active_b !== m.params_b && <div className="text-xs text-muted-foreground">aktywne {pb(m.active_b)}</div>}
                </TableCell>
                <TableCell className="px-3 text-right font-medium tabular-nums">{f1s(m.f1.train) ?? missing(m)}</TableCell>
                <TableCell className="px-3 text-right tabular-nums">{f1s(m.f1.blind) ?? missing(m)}</TableCell>
                <TableCell className="px-3 text-right tabular-nums">{usd(m.cost_usd?.train) ?? missing(m)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
