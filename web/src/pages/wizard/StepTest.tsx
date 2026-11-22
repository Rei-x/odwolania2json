import { useRef, useState, type ReactNode } from "react"
import { CheckCircle2, FileUp, Loader2, TriangleAlert } from "lucide-react"
import { Bar, BarChart, Cell, LabelList, XAxis, YAxis } from "recharts"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Card } from "@/components/ui/card"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"
import { JsonView } from "./JsonView"
import { typeColor, type Evidence, type TestResponse } from "./types"
import type { Wizard } from "./useWizard"
import { fmtSec, fmtUsd } from "@/lib/format"
import { displayValue, doctypeLabel, fieldLabel, pathLabel, prettyModel, sectionLabel, useDoctypeLabels } from "@/lib/labels"

const METHOD_DOT: Record<string, string> = { located: "bg-success", inferred: "bg-wheat", derived: "bg-sage" }

const CLS_CONFIG = {
  score: { label: "Wynik" },
  me: { label: "Nowy typ", color: "var(--primary)" },
  other: { label: "Inne typy", color: "var(--muted-foreground)" },
} satisfies ChartConfig

/** Rule-based classification scores as a compact horizontal bar chart (new type highlighted). */
function ClassChart({ scores, me }: { scores: [string, number][]; me: string }) {
  const data = scores.map(([name, score]) => ({ name, label: doctypeLabel(name), score }))
  return (
    <ChartContainer config={CLS_CONFIG} className="aspect-auto w-full" style={{ height: data.length * 26 + 4 }}>
      <BarChart data={data} layout="vertical" margin={{ left: 0, right: 28, top: 2, bottom: 2 }} barCategoryGap={5}>
        <XAxis type="number" hide domain={[0, "dataMax"]} />
        <YAxis
          type="category"
          dataKey="label"
          width={150}
          tickLine={false}
          axisLine={false}
          tick={{ fontSize: 11 }}
        />
        <ChartTooltip cursor={false} content={<ChartTooltipContent hideIndicator />} />
        <Bar dataKey="score" radius={6} minPointSize={3} isAnimationActive={false}>
          {data.map((r) => (
            <Cell key={r.name} fill={r.name === me ? "var(--color-me)" : "var(--color-other)"} fillOpacity={r.name === me ? 1 : 0.35} />
          ))}
          <LabelList dataKey="score" position="right" offset={6} className="fill-foreground" fontSize={11} />
        </Bar>
      </BarChart>
    </ChartContainer>
  )
}

function Dropzone({ name, onFile }: { name: string; onFile: (f: File) => void }) {
  const inp = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  return (
    <div className="mx-auto max-w-2xl space-y-3 py-6">
      <button
        type="button"
        onClick={() => inp.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          const f = [...e.dataTransfer.files].find((f) => /\.pdf$/i.test(f.name))
          if (f) onFile(f)
        }}
        className={cn(
          "flex w-full flex-col items-center gap-3 rounded-2xl border-2 border-dashed bg-card px-6 py-14 text-center transition-colors hover:border-primary/50 hover:bg-accent/40",
          over && "border-primary bg-accent/60",
        )}
      >
        <span className="grid size-14 place-items-center rounded-2xl bg-primary/10 text-primary">
          <FileUp className="size-7" />
        </span>
        <span className="font-medium">
          Upuść przykładowy PDF typu „{doctypeLabel(name)}”
        </span>
        <span className="text-sm text-muted-foreground">lub kliknij, aby wybrać</span>
      </button>
      <p className="text-center text-xs text-muted-foreground">Jedno wywołanie modelu · nic nie jest zapisywane</p>
      <input
        ref={inp}
        type="file"
        accept=".pdf"
        hidden
        data-testid="wz-file"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) onFile(f)
          e.target.value = ""
        }}
      />
    </div>
  )
}

function Busy({ name }: { name: string }) {
  return (
    <div className="flex flex-col items-center gap-3 py-24 text-center">
      <Loader2 className="size-8 animate-spin text-primary" />
      <b>Ekstrakcja szkicem „{doctypeLabel(name)}”…</b>
      <span className="text-sm text-muted-foreground">PDF → LLM → normalizacja → dowody</span>
    </div>
  )
}

function Row({ k, v, e, on, onPick }: { k: string; v: unknown; e?: Evidence; on: boolean; onPick: () => void }) {
  const isNull = v === null || v === undefined
  let evt: ReactNode
  if (!e) evt = "Brak w dokumencie."
  else if (e.method === "derived") evt = "Wyznaczone regułą z konfiguracji."
  else if (e.method === "inferred") evt = "Wywnioskowane przez model (brak dosłownego cytatu)."
  else {
    const ctx = e.context ?? ""
    const q = e.quote ?? ""
    const at = q ? ctx.indexOf(q) : -1
    evt = (
      <>
        str. {e.page} · „…
        {at >= 0 ? (
          <>
            {ctx.slice(0, at)}
            <mark className="rounded-sm bg-wheat/50 px-0.5 text-foreground">{q}</mark>
            {ctx.slice(at + q.length)}
          </>
        ) : (
          ctx
        )}
        …”
      </>
    )
  }
  return (
    <button
      type="button"
      onClick={onPick}
      className={cn("block w-full rounded-md px-3 py-1.5 text-left transition-colors hover:bg-secondary/70", on && "bg-accent hover:bg-accent")}
    >
      <span className="flex items-baseline gap-3">
        <span className="w-36 shrink-0 truncate text-xs text-muted-foreground">{k === "—" ? k : fieldLabel(k)}</span>
        <span className={cn("min-w-0 flex-1 text-sm break-words", isNull && "text-muted-foreground")}>{displayValue(k, v)}</span>
        <span className={cn("size-2 shrink-0 self-center rounded-full", e ? METHOD_DOT[e.method] ?? "bg-muted-foreground" : "opacity-0")} />
      </span>
      {on && <span className="mt-1 block pl-0 text-xs text-muted-foreground sm:pl-39">{evt}</span>}
    </button>
  )
}

function Fields({
  obj,
  path,
  depth,
  ev,
  picked,
  onPick,
}: {
  obj: Record<string, unknown>
  path: string
  depth: number
  ev: Record<string, Evidence>
  picked: string | null
  onPick: (p: string) => void
}): ReactNode {
  const out: ReactNode[] = []
  const head = (key: string, label: string, sub = false) => (
    <div key={key} className={cn("px-3 pt-3 pb-1 font-medium", sub ? "text-xs text-muted-foreground" : "text-xs tracking-wide text-primary uppercase")}>
      {label}
    </div>
  )
  for (const [k, v] of Object.entries(obj ?? {})) {
    const p = path ? `${path}.${k}` : k
    if (Array.isArray(v)) {
      if (!v.length) {
        out.push(head(p + ":h", sectionLabel(k)), <Row key={p} k="—" v={null} on={false} onPick={() => {}} />)
        continue
      }
      v.forEach((it, i) => {
        const ip = `${p}[${i}]`
        out.push(head(ip + ":h", v.length > 1 ? `${sectionLabel(k)} ${i + 1}` : sectionLabel(k)))
        if (it && typeof it === "object")
          out.push(<Fields key={ip} obj={it as Record<string, unknown>} path={ip} depth={depth + 1} ev={ev} picked={picked} onPick={onPick} />)
        else out.push(<Row key={ip} k={k} v={it} e={ev[ip]} on={picked === ip} onPick={() => onPick(ip)} />)
      })
    } else if (v && typeof v === "object") {
      out.push(head(p + ":h", depth > 0 ? fieldLabel(k) : sectionLabel(k), depth > 0), <Fields key={p} obj={v as Record<string, unknown>} path={p} depth={depth + 1} ev={ev} picked={picked} onPick={onPick} />)
    } else out.push(<Row key={p} k={k} v={v} e={ev[p]} on={picked === p} onPick={() => onPick(p)} />)
  }
  return <>{out}</>
}

function Result({ d }: { d: TestResponse }) {
  useDoctypeLabels()
  const t = d.trace
  const [view, setView] = useState<"dane" | "json">("dane")
  const [picked, setPicked] = useState<string | null>(null)
  const docRef = useRef<HTMLDivElement>(null)
  const ev: Record<string, Evidence> = {}
  for (const e of t.evidence ?? []) ev[e.field] = e
  const cls = t.classification ?? {}
  const scores = Object.entries(cls.scores ?? {})
  const chips = [`${t.pages} str.`, fmtSec(t.elapsed_s), prettyModel(t.model)]
  if (t.cost_usd) chips.push(fmtUsd(t.cost_usd))
  if (t.ocr_pages?.length) chips.push("OCR")
  const filled = (t.evidence ?? []).length
  const located = (t.evidence ?? []).filter((e) => e.method === "located").length
  const issues = t.issues ?? []
  const pickedEv = picked ? ev[picked] : undefined

  const pick = (p: string) => {
    const next = picked === p ? null : p
    setPicked(next)
    const e = next ? ev[next] : undefined
    if (!e?.page || !docRef.current) return
    const pg = docRef.current.querySelector<HTMLElement>(`[data-page="${e.page}"]`)
    if (!pg) return
    requestAnimationFrame(() => {
      const first = pg.querySelector<HTMLElement>("[data-hl]")
      const doc = docRef.current!
      doc.scrollTo({ top: pg.offsetTop + (first ? first.offsetTop - doc.clientHeight / 3 : 0), behavior: "smooth" })
      // on mobile the panel is not scrollable itself — bring the page into view instead
      if (doc.scrollHeight <= doc.clientHeight) pg.scrollIntoView({ behavior: "smooth", block: "center" })
    })
  }

  return (
    <div className="grid gap-5 lg:h-[calc(100svh-15rem)] lg:min-h-[520px] lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div ref={docRef} className="relative min-h-0 space-y-4 overflow-y-auto rounded-xl bg-secondary/60 p-3 max-lg:max-h-[70vh] sm:p-4">
        {Array.from({ length: t.pages || 1 }, (_, k) => (
          <div key={k} data-page={k + 1} className="relative overflow-hidden rounded-md bg-white shadow-sm ring-1 ring-foreground/10">
            <img loading="lazy" className="block w-full" src={`/api/page/${d.session}/${encodeURIComponent(d.file)}/${k + 1}.png`} alt={`Strona ${k + 1}`} />
            {pickedEv?.page === k + 1 &&
              (pickedEv.rects ?? []).map(([x, y, w, h], i) => (
                <div
                  key={i}
                  data-hl
                  className="absolute rounded-sm bg-primary/25 ring-2 ring-primary"
                  style={{ left: `${x}%`, top: `${y}%`, width: `${w}%`, height: `${h}%` }}
                />
              ))}
            <span className="absolute right-2 bottom-2 rounded-full bg-bark/80 px-2 py-0.5 font-mono text-[10px] text-white">
              {k + 1}/{t.pages}
            </span>
          </div>
        ))}
      </div>

      <Card className="min-h-0 gap-0 py-0">
        <div className="space-y-3 border-b p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className={cn("size-3 rounded-full", typeColor(d.doctype))} />
            <h2 className="text-lg font-semibold">{doctypeLabel(d.doctype)}</h2>
            <Tabs value={view} onValueChange={(v) => setView(v as "dane" | "json")} className="ml-auto">
              <TabsList>
                <TabsTrigger value="dane">Dane</TabsTrigger>
                <TabsTrigger value="json">JSON</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground tabular-nums">
            {chips.map((c) => (
              <span key={c}>{c}</span>
            ))}
            <span className="text-foreground">
              {located}/{filled} z cytatem
            </span>
          </div>
          <div className="space-y-1">
            <div className="flex flex-wrap items-baseline justify-between gap-x-2 text-xs">
              <span className="text-muted-foreground">Klasyfikacja regułami</span>
              {cls.confident ? (
                <span className="font-medium text-success">pewna</span>
              ) : cls.best === d.doctype ? (
                <span className="font-medium text-chart-3">mały margines — zdecyduje LLM</span>
              ) : (
                <span className="font-medium text-destructive">wygrywa „{doctypeLabel(cls.best)}” — dodaj słowa kluczowe</span>
              )}
            </div>
            <ClassChart scores={scores.slice(0, 5)} me={d.doctype} />
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {view === "json" ? (
            <JsonView value={d.result} className="p-2" />
          ) : (
            <>
              {issues.length ? (
                <div className="m-2 space-y-0.5 rounded-lg bg-wheat/20 p-3 text-xs">
                  <div className="flex items-center gap-1.5 font-medium">
                    <TriangleAlert className="size-3.5 text-chart-3" /> {issues.length} {issues.length === 1 ? "uwaga" : "uwagi"} walidatorów
                  </div>
                  <div className="text-muted-foreground">Po zapisie poprawi je pętla naprawy.</div>
                  {issues.map((i, k) => (
                    <div key={k}>
                      <span className="font-medium">{pathLabel(i.field)}</span>: {i.issue}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="m-2 flex items-center gap-1.5 text-xs text-success">
                  <CheckCircle2 className="size-3.5" /> Walidatory bez uwag
                </div>
              )}
              <Fields obj={d.result} path="" depth={0} ev={ev} picked={picked} onPick={pick} />
            </>
          )}
        </div>
      </Card>
    </div>
  )
}

export function StepTest({ wiz }: { wiz: Wizard }) {
  const { s } = wiz
  if (s.testing) return <Busy name={s.name} />
  if (!s.test) return <Dropzone name={s.name} onFile={wiz.runTest} />
  return <Result d={s.test} />
}
