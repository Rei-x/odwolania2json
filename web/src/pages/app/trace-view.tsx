import { useState } from "react"
import { Bar, BarChart, XAxis, YAxis } from "recharts"
import { AlertTriangle, Check, ChevronRight, Clock, Coins, Cpu, Download, Minus, ScanLine, X } from "lucide-react"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Button } from "@/components/ui/button"
import { type ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
import { cn } from "@/lib/utils"
import { type Doc, LABEL, shortModel } from "./lib"

/* eslint-disable @typescript-eslint/no-explicit-any */
type D = Record<string, any>
export type Step = {
  id: string
  label: string
  t_start: number
  duration_s: number
  model?: string | null
  models?: string[]
  calls?: number
  cost_usd?: number
  tokens?: { prompt: number; completion: number }
  error?: string
  detail: D
}
export type StepsSummary = {
  total_s: number
  llm_calls: number
  cost_usd: number
  tokens: { prompt: number; completion: number }
  models: string[]
}

const COLOR: Record<string, string> = {
  load: "var(--chart-5)",
  classify: "var(--chart-3)",
  few_shot: "var(--chart-4)",
  extract: "var(--chart-1)",
  normalize: "var(--chart-2)",
  ground: "var(--success)",
  verify: "var(--rust)",
  router: "var(--wheat)",
}
const color = (id: string) => COLOR[id] || "var(--muted-foreground)"

const sec = (s: number) => (s < 0.01 ? "<0,01 s" : s < 10 ? `${s.toFixed(2).replace(".", ",")} s` : `${s.toFixed(1).replace(".", ",")} s`)
const usd = (v: number) => v === 0 ? "$0" : `$${v < 0.001 ? v.toFixed(5) : v.toFixed(4)}`.replace(".", ",")
const pct = (v: number) => `${Math.round(v)}%`
const val = (v: unknown) => (v === null || v === undefined ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v))

/* ------------------------------------------------------------------ main view */

export function TraceView({ doc }: { doc: Doc }) {
  const steps = (doc.trace as D | undefined)?.steps as Step[] | undefined
  const summary = (doc.trace as D | undefined)?.steps_summary as StepsSummary | undefined
  if (!steps?.length)
    return <p className="p-4 text-sm text-muted-foreground">Brak zapisanego przebiegu dla tego dokumentu.</p>
  return (
    <div className="flex flex-col gap-3 px-2 py-3">
      <SummaryBar doc={doc} steps={steps} summary={summary} />
      <TimeBar steps={steps} />
      <Accordion multiple className="mt-1">
        {steps.map((s, i) => (
          <AccordionItem key={`${s.id}-${i}`} value={`${s.id}-${i}`} className="border-none">
            <StepRow step={s} last={i === steps.length - 1} />
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  )
}

function Stat({ icon, children, title }: { icon: React.ReactNode; children: React.ReactNode; title?: string }) {
  return (
    <span title={title} className="inline-flex items-center gap-1.5 text-sm tabular-nums [&_svg]:size-3.5 [&_svg]:text-muted-foreground">
      {icon}
      {children}
    </span>
  )
}

function SummaryBar({ doc, steps, summary }: { doc: Doc; steps: Step[]; summary?: StepsSummary }) {
  const total = summary?.total_s ?? steps.reduce((a, s) => Math.max(a, s.t_start + s.duration_s), 0)
  const tok = summary?.tokens
  return (
    <div className="mx-1 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl bg-muted/50 px-3 py-2.5">
      <Stat icon={<Clock />} title="Łączny czas">
        <b>{sec(total)}</b>
      </Stat>
      <Stat icon={<Cpu />} title={tok ? `Tokeny: ${tok.prompt} wejście / ${tok.completion} wyjście` : "Wywołania LLM"}>
        {summary?.llm_calls ?? 0} LLM
      </Stat>
      <Stat icon={<Coins />} title="Koszt wywołań LLM (wg dostawcy)">
        {usd(summary?.cost_usd ?? 0)}
      </Stat>
      <span className="flex min-w-0 flex-wrap gap-1">
        {(summary?.models || []).map((m) => (
          <span key={m} className="rounded-full bg-card px-2 py-0.5 font-mono text-[11px] ring-1 ring-border">
            {m === "deterministic" ? "reguły" : shortModel(m)}
          </span>
        ))}
      </span>
      {doc.session && (
        <Button
          variant="outline"
          size="sm"
          className="ml-auto rounded-full"
          nativeButton={false}
          render={
            <a
              href={`/api/trace/${doc.session}/${encodeURIComponent(doc.file)}`}
              download={doc.file.replace(/\.pdf$/i, ".trace.json")}
            />
          }
        >
          <Download /> Trace JSON
        </Button>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ where the time went */

function TimeBar({ steps }: { steps: Step[] }) {
  const keys = steps.map((s, i) => `${s.id}_${i}`)
  const config: ChartConfig = Object.fromEntries(
    steps.map((s, i) => [keys[i], { label: s.label, color: color(s.id) }]),
  )
  const row: D = { name: "czas" }
  steps.forEach((s, i) => (row[keys[i]] = Math.max(s.duration_s, 0.0005)))
  return (
    <div className="mx-1">
      <ChartContainer config={config} className="aspect-auto h-3 w-full">
        <BarChart data={[row]} layout="vertical" margin={{ top: 0, right: 0, bottom: 0, left: 0 }} barCategoryGap={0}>
          <XAxis type="number" hide domain={[0, "dataMax"]} />
          <YAxis type="category" dataKey="name" hide />
          <ChartTooltip
            cursor={false}
            content={
              <ChartTooltipContent
                hideLabel
                formatter={(v, name) => (
                  <span className="flex w-full items-center justify-between gap-3">
                    <span className="flex items-center gap-1.5">
                      <span className="size-2 rounded-[2px]" style={{ background: config[String(name)]?.color }} />
                      {config[String(name)]?.label}
                    </span>
                    <b className="tabular-nums">{sec(Number(v))}</b>
                  </span>
                )}
              />
            }
          />
          {keys.map((k, i) => (
            <Bar
              key={k}
              dataKey={k}
              stackId="t"
              fill={`var(--color-${k})`}
              radius={i === 0 ? [4, 0, 0, 4] : i === keys.length - 1 ? [0, 4, 4, 0] : 0}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ChartContainer>
    </div>
  )
}

/* ------------------------------------------------------------------ one step */

function StepRow({ step: s, last }: { step: Step; last: boolean }) {
  return (
    <div className="relative grid grid-cols-[20px_1fr] gap-x-2">
      <div className="relative flex justify-center">
        <span
          className="relative z-10 mt-[14px] size-2.5 rounded-full ring-4 ring-card"
          style={{ background: s.error ? "var(--destructive)" : color(s.id) }}
        />
        {!last && <span className="absolute top-[19px] bottom-[-19px] w-px bg-border" />}
      </div>
      <div className="min-w-0">
        <AccordionTrigger className="items-center gap-2 py-2 pr-1 hover:no-underline">
          <span className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="font-semibold">{s.label}</span>
            <span className="min-w-0 truncate text-xs font-normal text-muted-foreground">{headline(s)}</span>
          </span>
          <span className="flex shrink-0 items-center gap-1.5 text-xs font-normal text-muted-foreground tabular-nums">
            {s.model && s.model !== "deterministic" && (
              <span className="hidden rounded-full bg-muted px-1.5 py-px font-mono text-[10.5px] sm:inline">
                {shortModel(s.model)}
              </span>
            )}
            {!!s.cost_usd && <span className="hidden sm:inline">{usd(s.cost_usd)}</span>}
            <span className="w-14 text-right">{sec(s.duration_s)}</span>
          </span>
        </AccordionTrigger>
        <AccordionContent className="pr-1">
          {s.error && (
            <p className="mb-2 rounded-md bg-destructive/10 px-2 py-1.5 font-mono text-xs break-all text-destructive">{s.error}</p>
          )}
          <StepMeta s={s} />
          <StepDetail s={s} />
        </AccordionContent>
      </div>
    </div>
  )
}

function StepMeta({ s }: { s: Step }) {
  if (!s.calls) return null
  return (
    <div className="mb-2 flex flex-wrap gap-1.5 text-[11px] text-muted-foreground">
      <Chip>{s.calls}× LLM</Chip>
      {(s.models || []).map((m) => (
        <Chip key={m} mono>
          {m}
        </Chip>
      ))}
      {s.tokens && (
        <Chip>
          {s.tokens.prompt} → {s.tokens.completion} tok.
        </Chip>
      )}
      {!!s.cost_usd && <Chip>{usd(s.cost_usd)}</Chip>}
    </div>
  )
}

function Chip({ children, mono, className }: { children: React.ReactNode; mono?: boolean; className?: string }) {
  return (
    <span className={cn("rounded-full bg-muted px-2 py-0.5 text-[11px] text-secondary-foreground", mono && "font-mono", className)}>
      {children}
    </span>
  )
}

function headline(s: Step): string {
  const d = s.detail || {}
  switch (s.id) {
    case "load": {
      const ocr = (d.ocr_pages || []).length
      return `${d.n_pages ?? 0} str. · ${ocr ? `OCR ${ocr} str.` : "warstwa tekstowa"}`
    }
    case "classify":
      return d.out_of_scope
        ? "poza zakresem → {}"
        : `${LABEL[d.decision] || d.decision}${d.confident === false ? " · niepewna" : ""}`
    case "few_shot": {
      const ex = d.examples || []
      return ex.length ? `${ex.length} · najbliższy ${pct(ex[0].similarity)}` : "bez przykładów"
    }
    case "extract":
      return [d.voting ? `głosowanie ${d.voting.runs ?? ""}` : null, d.retries ? `${d.retries} ponowienia` : null, d.skipped]
        .filter(Boolean)
        .join(" · ") || (d.fill_ratio != null ? `wypełnienie ${pct(d.fill_ratio * 100)}` : "")
    case "normalize": {
      const n = (d.normalized || []).length + (d.snap_to_text || []).length + (d.rules_fill || []).length
      return n ? `${n} zmian` : "bez zmian"
    }
    case "ground": {
      const c = d.counts || {}
      return [c.located && `${c.located} cytatów`, c.inferred && `${c.inferred} wywnioskowanych`, c.derived && `${c.derived} z reguł`]
        .filter(Boolean)
        .join(" · ")
    }
    case "verify": {
      const r = (d.rounds || []).length
      const left = (d.remaining_issues || []).length
      return r ? `${r} ${r === 1 ? "runda" : "rundy"}${left ? ` · ${left} uwag zostało` : " · naprawiono"}` : d.max_rounds === 0 ? "wyłączona" : "bez uwag"
    }
    case "router":
      return d.escalate ? `eskalacja → ${(d.vote?.steps || []).map((x: D) => x.models.map(shortModel).join("+")).join(" → ")}` : "bez eskalacji"
  }
  return ""
}

/* ------------------------------------------------------------------ step details */

function StepDetail({ s }: { s: Step }) {
  const d = s.detail || {}
  switch (s.id) {
    case "load":
      return <LoadDetail d={d} />
    case "classify":
      return <ClassifyDetail d={d} />
    case "few_shot":
      return <FewShotDetail d={d} />
    case "extract":
      return <ExtractDetail d={d} />
    case "normalize":
      return <NormalizeDetail d={d} />
    case "ground":
      return <GroundDetail d={d} />
    case "verify":
      return <VerifyDetail d={d} />
    case "router":
      return <RouterDetail d={d} />
  }
  return <JsonBlock data={d} />
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-2 first:mt-0">
      <div className="mb-1 text-[10.5px] font-semibold tracking-wider text-muted-foreground uppercase">{title}</div>
      {children}
    </div>
  )
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-muted-foreground">{children}</p>
}

function JsonBlock({ data, text, label = "Pokaż JSON" }: { data?: unknown; text?: string; label?: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ChevronRight className={cn("size-3 transition-transform", open && "rotate-90")} />
        {label}
      </button>
      {open && (
        <pre className="mt-1 max-h-80 overflow-auto rounded-md bg-muted/60 p-2.5 font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap break-all">
          {text ?? JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  )
}

function DiffList({ items, empty = "Bez zmian." }: { items?: D[]; empty?: string }) {
  if (!items?.length) return <Empty>{empty}</Empty>
  return (
    <div className="flex flex-col gap-1">
      {items.map((c, i) => (
        <div key={i} className="rounded-md bg-muted/40 px-2 py-1.5 text-xs">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-mono text-[11px] text-muted-foreground">{c.field}</span>
            {c.rule && <Chip className="py-0 text-[10px]">{c.rule}</Chip>}
          </div>
          <div className="mt-0.5 break-words">
            <s className="text-muted-foreground">{val(c.before)}</s> <span className="text-muted-foreground">→</span>{" "}
            <b>{val(c.after)}</b>
          </div>
          {c.reason && <div className="mt-0.5 text-[11px] text-muted-foreground italic">„{c.reason}”</div>}
        </div>
      ))}
    </div>
  )
}

function LoadDetail({ d }: { d: D }) {
  return (
    <div className="flex flex-col gap-1.5">
      {(d.preprocess || []).length > 0 && (d.ocr_pages || []).length > 0 && (
        <div className="text-xs text-muted-foreground">Przygotowanie skanu: {d.preprocess.join(", ")}</div>
      )}
      {d.load_error && <p className="font-mono text-xs text-destructive">{d.load_error}</p>}
      {(d.pages || []).map((p: D) => (
        <div key={p.page} className="rounded-md bg-muted/40 px-2.5 py-2 text-xs">
          <div className="flex flex-wrap items-center gap-1.5">
            <b>str. {p.page}</b>
            <Chip className={p.source === "ocr" ? "bg-wheat/30 text-bark" : ""}>
              {p.source === "ocr" ? (
                <>
                  <ScanLine className="mr-0.5 inline size-3" />
                  OCR
                </>
              ) : (
                "tekst"
              )}
            </Chip>
            <span className="text-muted-foreground tabular-nums">{p.chars} zn.</span>
            {p.scan && <Chip>skan (brak warstwy tekstowej)</Chip>}
            {p.garbled && <Chip className="bg-destructive/10 text-destructive">zepsute kodowanie · jakość {p.quality}</Chip>}
            {p.mojibake_fixed && <Chip>naprawiono kodowanie (cp1250)</Chip>}
            {p.annotation_chars > 0 && <Chip>adnotacje +{p.annotation_chars} zn.</Chip>}
            {p.orientation && p.orientation.angle !== 0 && (
              <Chip>obrót {p.orientation.angle}°{p.orientation.prob ? ` (${pct(p.orientation.prob * 100)})` : ""}</Chip>
            )}
            {p.ocr && (
              <span className="ml-auto flex items-center gap-1.5 text-muted-foreground tabular-nums">
                {p.ocr.model ? <span className="font-mono text-[10.5px]">{shortModel(p.ocr.model)}</span> : p.ocr.engine}
                {p.ocr.duration_s != null && <span>{sec(p.ocr.duration_s)}</span>}
                {!!p.ocr.cost_usd && <span>{usd(p.ocr.cost_usd)}</span>}
              </span>
            )}
          </div>
          {p.preview && (
            <pre className="mt-1.5 max-h-28 overflow-auto font-mono text-[11px] leading-snug whitespace-pre-wrap text-secondary-foreground">
              {p.preview}
            </pre>
          )}
        </div>
      ))}
    </div>
  )
}

function ClassifyDetail({ d }: { d: D }) {
  const scores = Object.entries((d.scores || {}) as Record<string, number>).sort((a, b) => b[1] - a[1])
  const max = Math.max(1, ...scores.map(([, v]) => v))
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-1.5 text-xs">
        <b className="text-sm">{d.out_of_scope ? "poza zakresem" : LABEL[d.decision] || d.decision}</b>
        {d.confident ? <Chip className="bg-success/15 text-success">reguły pewne</Chip> : <Chip>reguły niepewne</Chip>}
        {d.method && <Chip>{d.method}</Chip>}
        {d.out_of_scope && <Chip className="bg-wheat/30 text-bark">wynik: {"{}"}</Chip>}
      </div>
      <Section title={`Punkty reguł (próg ${d.min_score ?? "?"})`}>
        <div className="flex flex-col gap-1.5">
          {scores.map(([name, v]) => (
            <div key={name} className="text-xs">
              <div className="flex items-center gap-2">
                <span className="w-28 shrink-0">{LABEL[name] || name}</span>
                <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                  <span
                    className="block h-full rounded-full"
                    style={{ width: `${(v / max) * 100}%`, background: name === d.decision ? "var(--primary)" : "var(--chart-5)" }}
                  />
                </span>
                <span className="w-8 text-right tabular-nums">{v}</span>
              </div>
              {(d.matched_keywords?.[name] || []).length > 0 && (
                <div className="mt-0.5 flex flex-wrap gap-1 pl-[7.5rem] max-sm:pl-0">
                  {d.matched_keywords[name].slice(0, 8).map((k: string) => (
                    <code key={k} className="max-w-full rounded bg-muted px-1 text-[10.5px] break-all text-muted-foreground">
                      {k}
                    </code>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </Section>
      {d.llm_votes && (
        <Section title="Głosy">
          <div className="flex flex-wrap gap-1">
            {d.llm_votes.map((v: string, i: number) => (
              <Chip key={i} className={v === d.decision ? "bg-primary/10 text-primary" : ""}>
                {LABEL[v] || v}
              </Chip>
            ))}
          </div>
        </Section>
      )}
      {d.llm_errors && <p className="mt-1 font-mono text-[11px] text-destructive">{d.llm_errors.join("; ")}</p>}
    </div>
  )
}

function FewShotDetail({ d }: { d: D }) {
  const ex = d.examples || []
  if (!ex.length) return <Empty>Model działał bez przykładów.</Empty>
  return (
    <div className="flex flex-col gap-1">
      {ex.map((e: D) => (
        <div key={e.name} className="flex items-center gap-2 text-xs">
          <span className="w-36 shrink-0 truncate font-mono text-[11px]">{e.name.replace(/^learned:/, "pamięć:")}</span>
          <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
            <span className="block h-full rounded-full bg-chart-4" style={{ width: `${Math.min(100, e.similarity)}%` }} />
          </span>
          <span className="w-10 text-right tabular-nums">{pct(e.similarity)}</span>
        </div>
      ))}
      <p className="mt-1 text-[11px] text-muted-foreground">Z pamięci dostępnych: {d.learned_available ?? 0}</p>
    </div>
  )
}

function ExtractDetail({ d }: { d: D }) {
  return (
    <div>
      <div className="flex flex-wrap gap-1.5">
        {d.prompt_chars && <Chip>prompt ≈ {d.prompt_tokens_est} tok.</Chip>}
        {d.few_shot != null && <Chip>{d.few_shot} przykł.</Chip>}
        {!!d.images && <Chip>{d.images} obrazów stron</Chip>}
        {d.attempts > 1 && <Chip>{d.attempts} próby JSON</Chip>}
        {!!d.retries && <Chip>{d.retries} ponowienia (puste)</Chip>}
        {d.pages_read != null && <Chip>{d.pages_read} str. czytanych</Chip>}
        {d.skipped && <Chip>{d.skipped}</Chip>}
      </div>
      {d.voting && (
        <Section title="Głosowanie">
          <div className="text-xs text-muted-foreground">
            {d.voting.runs} przebiegów · {(d.voting.models || []).map(shortModel).join(", ")}
            {d.voting.disagreements?.length ? ` · spory: ${d.voting.disagreements.length}` : ""}
          </div>
        </Section>
      )}
      {d.raw_output && <JsonBlock data={d.raw_output} label="Surowy JSON modelu" />}
      {(d.raw_outputs || []).map((r: D, i: number) => (
        <JsonBlock key={i} text={r.raw} label={`Przebieg ${i + 1} · ${shortModel(r.model || "")}`} />
      ))}
    </div>
  )
}

function NormalizeDetail({ d }: { d: D }) {
  return (
    <div>
      <Section title="Schemat (formaty, mianownik, cyfry)">
        <DiffList items={d.normalized} />
      </Section>
      {d.snap_to_text && (
        <Section title="Dopasowanie do tekstu">
          <DiffList items={d.snap_to_text} />
        </Section>
      )}
      {d.rules_fill && (
        <Section title="Uzupełnione regułami">
          <DiffList items={d.rules_fill} />
        </Section>
      )}
    </div>
  )
}

const METHOD_ICON: Record<string, React.ReactNode> = {
  located: <Check className="size-3 text-success" />,
  inferred: <AlertTriangle className="size-3 text-wheat" />,
  derived: <Minus className="size-3 text-muted-foreground" />,
}

function GroundDetail({ d }: { d: D }) {
  const fields: D[] = d.fields || []
  if (!fields.length) return <Empty>Brak pól.</Empty>
  return (
    <div className="flex flex-col">
      {fields.map((f) => (
        <div key={f.field} className="grid grid-cols-[14px_minmax(0,40%)_1fr] items-baseline gap-x-2 py-0.5 text-xs">
          <span className="self-center">{METHOD_ICON[f.method] || <X className="size-3 text-destructive" />}</span>
          <span className="truncate font-mono text-[11px] text-muted-foreground" title={f.field}>
            {f.field}
          </span>
          <span className="min-w-0 truncate">
            {f.page ? <span className="text-muted-foreground">s.{f.page} </span> : null}
            {f.quote || (f.method === "inferred" ? "wywnioskowane" : f.method === "derived" ? "reguła" : "—")}
          </span>
        </div>
      ))}
    </div>
  )
}

function VerifyDetail({ d }: { d: D }) {
  const rounds: D[] = d.rounds || []
  return (
    <div>
      {!rounds.length && <Empty>{d.max_rounds === 0 ? "Profil bez pętli naprawy." : "Weryfikacja nie znalazła problemów."}</Empty>}
      {rounds.map((r, i) => (
        <Section key={i} title={`Runda ${i + 1}`}>
          <div className="mb-1 flex flex-col gap-0.5">
            {(r.issues || []).map((x: D, j: number) => (
              <div key={j} className="text-xs">
                <span className="font-mono text-[11px] text-muted-foreground">{x.field}</span> = {val(x.value)}{" "}
                <span className="text-rust">· {x.issue}</span>
              </div>
            ))}
          </div>
          {r.error ? <p className="font-mono text-[11px] text-destructive">{r.error}</p> : <DiffList items={r.changes} empty="Model nie zmienił pól." />}
        </Section>
      ))}
      {(d.remaining_issues || []).length > 0 && (
        <Section title="Pozostałe uwagi">
          {d.remaining_issues.map((x: D, j: number) => (
            <div key={j} className="text-xs">
              <span className="font-mono text-[11px] text-muted-foreground">{x.field}</span> · {x.issue}
            </div>
          ))}
        </Section>
      )}
    </div>
  )
}

function RouterDetail({ d }: { d: D }) {
  return (
    <div>
      <Section title="Sygnały trudności">
        {(d.reasons || []).length ? (
          <ul className="flex flex-col gap-0.5 text-xs">
            {d.reasons.map((r: string) => (
              <li key={r}>• {r}</li>
            ))}
          </ul>
        ) : (
          <Empty>Łatwy dokument.</Empty>
        )}
        {(d.disputed || []).length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {d.disputed.map((f: string) => (
              <code key={f} className="rounded bg-muted px-1 text-[10.5px] text-muted-foreground">
                {f}
              </code>
            ))}
          </div>
        )}
      </Section>
      {d.vote && (
        <Section title="Eskalacja">
          {(d.vote.steps || []).map((s: D) => (
            <div key={s.level} className="text-xs">
              poziom {s.level}: <span className="font-mono text-[11px]">{s.models.map(shortModel).join(" + ")}</span>
              {s.disagreed_with_previous?.length ? ` · różnice: ${s.disagreed_with_previous.length}` : " · potwierdził"}
            </div>
          ))}
          <div className="text-[11px] text-muted-foreground">głosujących: {d.vote.voters}</div>
        </Section>
      )}
      {d.changes && (
        <Section title="Zmiany po głosowaniu">
          <DiffList items={d.changes} />
        </Section>
      )}
    </div>
  )
}

