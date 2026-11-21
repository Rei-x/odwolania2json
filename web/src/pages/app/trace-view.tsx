import { useState } from "react"
import { Bar, BarChart, XAxis, YAxis } from "recharts"
import { AlertTriangle, Check, ChevronRight, Download, Minus, PencilLine, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { type ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
import { cn } from "@/lib/utils"
import { type Doc, LABEL, shortModel } from "./lib"

/*
 * "Przebieg": what happened to the document, readable by a non-technical person in a few seconds.
 * Layout inspired by Browserbase agent runs (outcome + duration + time strip on top, one row per step),
 * the Webflow deploy stepper (status circle + one plain sentence) and H&M order tracking (numbered steps).
 * Technical data (rule patterns, raw JSON, tokens, model ids) stays behind "Szczegóły techniczne".
 */

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
type Status = "ok" | "changed" | "warn" | "error"
type Change = { field: string; before: unknown; after: unknown; reason?: string }

const TITLE: Record<string, string> = {
  load: "Wczytanie",
  classify: "Klasyfikacja",
  extract: "Ekstrakcja",
  normalize: "Normalizacja",
  ground: "Dowody",
  verify: "Weryfikacja",
  router: "Router",
}

/* ------------------------------------------------------------------ formatting */

const sec = (s: number) =>
  s < 0.01 ? "<0,01 s" : s < 10 ? `${s.toFixed(2).replace(".", ",")} s` : `${s.toFixed(1).replace(".", ",")} s`
const usd = (v: number) => (v === 0 ? "$0" : `$${v < 0.001 ? v.toFixed(5) : v.toFixed(4)}`.replace(".", ","))
const pct = (v: number) => `${Math.round(v)}%`
const val = (v: unknown) => (v === null || v === undefined ? "brak" : typeof v === "object" ? JSON.stringify(v) : String(v))
const plural = (n: number, one: string, few: string, many: string) =>
  n === 1 ? one : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? few : many

/** "mistralai/ministral-8b-2512" -> "Ministral 8B" */
export function prettyModel(id?: string | null): string {
  if (!id) return ""
  if (id === "deterministic") return "reguły"
  const base = shortModel(id).replace(/[-_:]?\d{4}$/, "").replace(/-(it|instruct|chat)$/i, "")
  return base
    .split(/[-_]/)
    .filter(Boolean)
    .map((t) => (/^\d+(\.\d+)?[bkmt]$/i.test(t) || /^a\d+b$/i.test(t) ? t.toUpperCase() : t[0].toUpperCase() + t.slice(1)))
    .join(" ")
}

/** Field path -> short readable name: "Odwolujacy[0].pelnomocnik.imie_nazwisko" -> "pełnomocnik · imię i nazwisko" */
const NICE: Record<string, string> = {
  imie_nazwisko: "imię i nazwisko",
  numer_postepowania: "nr postępowania",
  numer_bzp: "nr BZP",
  numer_ted: "nr TED",
  czynnosc_dzien: "data czynności",
  czynnosc_opis: "czynność",
  czynnosc_powod_id: "powód",
  data_operacji: "data operacji",
  na_rachunek: "na rachunek",
  z_rachunku: "z rachunku",
  numer_transakcji: "nr transakcji",
  miejscowosc: "miejscowość",
  pelnomocnik: "pełnomocnik",
  pelnomocnicy: "pełnomocnik",
  podpisujacy: "podpisujący",
  Odwolujacy: "odwołujący",
  Zamawiajacy: "zamawiający",
  mocodawca: "mocodawca",
  tytul: "tytuł",
}
function fieldName(path: string): string {
  const parts = path.replace(/\[\d+\]/g, "").split(".")
  const leaf = parts[parts.length - 1]
  const parent = parts.length > 1 ? parts[parts.length - 2] : ""
  const n = (k: string) => NICE[k] ?? k.replaceAll("_", " ").replaceAll("-", " ")
  const showParent = parent && !/^(OdwolanieKIO|ZamowieniePubliczne|przelew_bankowy|data)$/.test(parent)
  return showParent ? `${n(parent)} · ${n(leaf)}` : n(leaf)
}

function leaves(x: unknown, out: unknown[] = []): unknown[] {
  if (Array.isArray(x)) x.forEach((v) => leaves(v, out))
  else if (x && typeof x === "object") Object.values(x).forEach((v) => leaves(v, out))
  else out.push(x)
  return out
}

/* ------------------------------------------------------------------ plain-language model of the run */

type View = {
  key: string
  title: string
  usesModel: boolean
  status: Status
  sentence: string
  note?: string
  changes: Change[]
  duration: number
  steps: Step[] // underlying backend steps (few-shot is folded into extraction)
}

function build(steps: Step[], doc: Doc): View[] {
  const few = steps.find((s) => s.id === "few_shot")
  const out: View[] = []
  for (const s of steps) {
    if (s.id === "few_shot") continue
    const d = s.detail || {}
    const parts = s.id === "extract" && few ? [few, s] : [s]
    const usesModel = parts.some((p) => !!p.calls)
    const v: View = {
      key: s.id,
      title: TITLE[s.id] || s.label,
      usesModel,
      status: "ok",
      sentence: "",
      changes: [],
      duration: parts.reduce((a, p) => a + p.duration_s, 0),
      steps: parts,
    }
    const models = [...new Set(parts.flatMap((p) => p.models || []))].map(prettyModel)
    switch (s.id) {
      case "load": {
        const n = d.n_pages ?? 0
        const ocr = (d.ocr_pages || []).length
        const pages = (d.pages || []) as D[]
        const rotated = pages.filter((p) => p.orientation && p.orientation.angle)
        const fixed = pages.filter((p) => p.mojibake_fixed).length
        const garbled = pages.filter((p) => p.garbled).length
        const ocrInfo = pages.find((p) => p.ocr)?.ocr
        const strony = `${n} ${plural(n, "strona", "strony", "stron")}`
        v.sentence = ocr
          ? `${strony}, ${ocr === n ? "skan" : `${ocr} ze skanu`} odczytany przez OCR${
              ocrInfo?.model ? ` (${prettyModel(ocrInfo.model)})` : ocrInfo?.engine ? " (lokalnie)" : ""
            }`
          : `${strony}, tekst z PDF (bez OCR)`
        const notes = [
          rotated.length ? `obrócono ${rotated.length === 1 ? "stronę" : "strony"} o ${rotated[0].orientation.angle}°` : "",
          fixed ? "naprawiono polskie znaki" : "",
          garbled ? "zepsuta warstwa tekstowa, użyto OCR" : "",
        ].filter(Boolean)
        v.note = notes.join(" · ") || undefined
        v.status = notes.length ? "changed" : "ok"
        if (d.load_error) {
          v.sentence = "Nie udało się odczytać pliku"
          v.status = "error"
        }
        break
      }
      case "classify": {
        const name = LABEL[d.decision] || d.decision
        const votes = (d.llm_votes || []) as string[]
        const llmAgrees = votes.length > 0 && votes.every((x) => x === d.decision)
        if (d.out_of_scope) {
          v.sentence = "Poza zakresem: to nie jest odwołanie, pełnomocnictwo ani przelew, więc wynik to pusty JSON {}"
          v.status = "warn"
        } else {
          const how = d.confident ? "pewne (reguły)" : "reguły niepewne"
          const model = votes.length ? (llmAgrees ? ", model potwierdził" : ", rozstrzygnął model") : ""
          v.sentence = `${name}, ${how}${model}`
          v.status = d.confident || llmAgrees ? "ok" : "warn"
        }
        break
      }
      case "extract": {
        const vals = leaves(doc.result || {})
        const filled = vals.filter((x) => x !== null && x !== "").length
        const ex = (few?.detail?.examples || []) as D[]
        const who = usesModel ? models.join(" + ") || "model" : "reguły z konfiguracji"
        v.sentence = d.skipped ? `Pominięto: ${d.skipped}` : `${filled} z ${vals.length} pól wypełnionych · ${who}`
        const notes = [
          ex.length ? `na wzór ${ex.length} ${plural(ex.length, "podobnego dokumentu", "podobnych dokumentów", "podobnych dokumentów")}` : "",
          d.voting ? `głosowanie ${d.voting.runs ?? ""} przebiegów` : "",
          d.retries ? `ponowiono ${d.retries}×` : "",
          d.images ? `model widział obraz ${d.images === 1 ? "strony" : "stron"}` : "",
        ].filter(Boolean)
        v.note = notes.join(" · ") || undefined
        v.status = d.skipped || (vals.length && filled / vals.length < 0.5) ? "warn" : "ok"
        break
      }
      case "normalize": {
        const ch: Change[] = [...(d.normalized || []), ...(d.snap_to_text || []), ...(d.rules_fill || [])].filter(
          (c: Change) => !(c.before == null && c.after == null),
        )
        v.changes = ch
        v.sentence = ch.length
          ? `${ch.length} ${plural(ch.length, "pole ujednolicone", "pola ujednolicone", "pól ujednoliconych")} (daty, numery, odmiana)`
          : "Wartości już w poprawnym formacie"
        v.status = ch.length ? "changed" : "ok"
        break
      }
      case "ground": {
        const c = d.counts || {}
        const total = (d.fields || []).length
        const loc = c.located || 0
        v.sentence = total ? `${loc} z ${total} wartości ma cytat w dokumencie` : "Brak wartości do potwierdzenia"
        const notes = [
          c.inferred ? `${c.inferred} ${plural(c.inferred, "wywnioskowana", "wywnioskowane", "wywnioskowanych")} przez model` : "",
          c.derived ? `${c.derived} z reguły` : "",
        ].filter(Boolean)
        v.note = notes.join(" · ") || undefined
        v.status = total && loc / total < 0.6 ? "warn" : "ok"
        break
      }
      case "verify": {
        const rounds = (d.rounds || []) as D[]
        const fixes: Change[] = rounds.flatMap((r) => r.changes || [])
        const left = (d.remaining_issues || []).length
        v.changes = fixes
        if (d.max_rounds === 0 && !rounds.length) v.sentence = "Wyłączona w tym profilu"
        else if (!rounds.length) v.sentence = "Bez uwag: formaty i wartości się zgadzają"
        else
          v.sentence = fixes.length
            ? `${fixes.length} ${plural(fixes.length, "pole poprawione", "pola poprawione", "pól poprawionych")} przez model`
            : `Znaleziono ${rounds[0].issues?.length ?? 0} uwag, model nic nie zmienił`
        if (left) v.note = `${left} ${plural(left, "uwaga pozostała", "uwagi pozostały", "uwag pozostało")} do sprawdzenia`
        v.status = rounds.some((r) => r.error) || left ? "warn" : fixes.length ? "changed" : "ok"
        break
      }
      case "router": {
        if (d.escalate) {
          const target = (d.vote?.steps || []).map((x: D) => x.models.map(prettyModel).join(" + ")).join(" → ")
          v.sentence = `Eskalacja do ${target || "mocniejszego modelu"}, bo ${(d.reasons || [])[0] || "dokument jest trudny"}`
          v.changes = d.changes || []
          v.status = "changed"
        } else {
          v.sentence = "Bez eskalacji: łatwy dokument"
        }
        break
      }
    }
    const failed = parts.find((p) => p.error)
    if (failed) {
      v.status = "error"
      v.note = "Przerwano: " + friendlyError(failed.error!)
    }
    out.push(v)
  }
  return out
}

function friendlyError(e: string) {
  if (/402|credits/i.test(e)) return "brak środków na koncie dostawcy modeli"
  if (/401|403/.test(e)) return "dostawca modeli odrzucił klucz"
  if (/timeout/i.test(e)) return "przekroczono czas odpowiedzi modelu"
  return e.length > 120 ? e.slice(0, 120) + "…" : e
}

/* ------------------------------------------------------------------ main view */

export function TraceView({ doc }: { doc: Doc }) {
  const steps = (doc.trace as D | undefined)?.steps as Step[] | undefined
  const summary = (doc.trace as D | undefined)?.steps_summary as StepsSummary | undefined
  if (!steps?.length)
    return <p className="p-4 text-sm text-muted-foreground">Brak zapisanego przebiegu dla tego dokumentu.</p>
  const views = build(steps, doc)
  return (
    <div className="flex min-w-0 flex-col gap-4 px-2 py-3">
      <Summary doc={doc} views={views} summary={summary} />
      <ol className="flex min-w-0 flex-col px-1">
        {views.map((v, i) => (
          <StepItem key={v.key} v={v} n={i + 1} last={i === views.length - 1} />
        ))}
      </ol>
    </div>
  )
}

/* ------------------------------------------------------------------ summary */

const stepColor = (v: View) => (v.usesModel ? "var(--primary)" : "var(--sage)")

function Summary({ doc, views, summary }: { doc: Doc; views: View[]; summary?: StepsSummary }) {
  const total = summary?.total_s ?? views.reduce((a, v) => a + v.duration, 0)
  const models = (summary?.models || []).filter((m) => m !== "deterministic")
  const calls = summary?.llm_calls ?? 0
  const failed = views.some((v) => v.status === "error")
  return (
    <div className="mx-1 flex flex-col gap-3 rounded-xl bg-muted/50 px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <p className="text-base font-semibold">
            {failed ? "Przetwarzanie przerwane" : "Dokument przetworzony"} w {sec(total)}
          </p>
          <p className="text-sm text-muted-foreground">
            {calls
              ? `${calls} ${plural(calls, "zapytanie", "zapytania", "zapytań")} do modelu AI (${models.map(prettyModel).join(", ")}) · koszt ${usd(summary?.cost_usd ?? 0)}`
              : "Bez modelu AI, tylko reguły · koszt $0"}
          </p>
        </div>
        {doc.session && (
          <Button
            variant="outline"
            size="sm"
            className="shrink-0 rounded-full"
            nativeButton={false}
            render={
              <a
                href={`/api/trace/${doc.session}/${encodeURIComponent(doc.file)}`}
                download={doc.file.replace(/\.pdf$/i, ".trace.json")}
              />
            }
          >
            <Download /> Pobierz przebieg (JSON)
          </Button>
        )}
      </div>
      <TimeBar views={views} />
    </div>
  )
}

function TimeBar({ views }: { views: View[] }) {
  const config: ChartConfig = Object.fromEntries(views.map((v) => [v.key, { label: v.title, color: stepColor(v) }]))
  const row: D = { name: "czas" }
  views.forEach((v) => (row[v.key] = Math.max(v.duration, 0.0005)))
  const total = views.reduce((a, v) => a + v.duration, 0) || 1
  return (
    <div>
      <ChartContainer config={config} className="aspect-auto h-2.5 w-full">
        <BarChart data={[row]} layout="vertical" margin={{ top: 0, right: 0, bottom: 0, left: 0 }} barCategoryGap={0}>
          <XAxis type="number" hide domain={[0, "dataMax"]} />
          <YAxis type="category" dataKey="name" hide />
          <ChartTooltip
            cursor={false}
            content={
              <ChartTooltipContent
                hideLabel
                formatter={(value, name) => (
                  <span className="flex w-full items-center justify-between gap-3">
                    <span>{config[String(name)]?.label}</span>
                    <b className="tabular-nums">{sec(Number(value))}</b>
                  </span>
                )}
              />
            }
          />
          {views.map((v, i) => (
            <Bar
              key={v.key}
              dataKey={v.key}
              stackId="t"
              fill={`var(--color-${v.key})`}
              stroke="var(--card)"
              strokeWidth={1.5}
              radius={i === 0 ? [4, 0, 0, 4] : i === views.length - 1 ? [0, 4, 4, 0] : 0}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ChartContainer>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11.5px] text-muted-foreground">
        {views
          .filter((v) => v.duration / total >= 0.03)
          .map((v) => (
            <span key={v.key} className="inline-flex items-center gap-1.5">
              <span className="size-2 rounded-[2px]" style={{ background: stepColor(v) }} />
              {v.title} <span className="tabular-nums">{sec(v.duration)}</span>
            </span>
          ))}
        <span className="ml-auto inline-flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-sage" /> kod
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-primary" /> model AI
          </span>
        </span>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ one step */

const STATUS_ICON: Record<Status, React.ReactNode> = {
  ok: <Check className="size-3.5" strokeWidth={3} />,
  changed: <PencilLine className="size-3.5" strokeWidth={2.5} />,
  warn: <AlertTriangle className="size-3.5" strokeWidth={2.5} />,
  error: <X className="size-3.5" strokeWidth={3} />,
}
const STATUS_LABEL: Record<Status, string> = {
  ok: "gotowe",
  changed: "coś zmieniono",
  warn: "uwaga",
  error: "błąd",
}

function StepItem({ v, n, last }: { v: View; n: number; last: boolean }) {
  const bg = v.status === "error" ? "var(--destructive)" : v.status === "warn" ? "var(--wheat)" : stepColor(v)
  return (
    <li className="grid min-w-0 grid-cols-[28px_minmax(0,1fr)] gap-x-3">
      <div className="relative flex justify-center">
        <span
          className="relative z-10 grid size-7 place-items-center rounded-full text-white"
          style={{ background: bg }}
          title={`${STATUS_LABEL[v.status]} · ${v.usesModel ? "krok z modelem AI" : "krok wykonany kodem"}`}
        >
          {STATUS_ICON[v.status]}
        </span>
        {!last && <span className="absolute top-7 bottom-0 w-0.5 rounded-full bg-foreground/10" />}
      </div>
      <div className={cn("min-w-0", last ? "pb-1" : "pb-5")}>
        <div className="flex min-w-0 items-center gap-2 pt-1">
          <h3 className="font-semibold">
            <span className="mr-1.5 text-xs font-normal text-muted-foreground tabular-nums">{n}.</span>
            {v.title}
          </h3>
          <span
            className={cn(
              "rounded-full px-1.5 py-px text-[10.5px] font-medium",
              v.usesModel ? "bg-primary/10 text-primary" : "bg-sage/15 text-sage",
            )}
          >
            {v.usesModel ? "model AI" : "kod"}
          </span>
          <span className="ml-auto shrink-0 text-xs text-muted-foreground tabular-nums">{sec(v.duration)}</span>
        </div>
        <p className="mt-0.5 text-sm break-words">{v.sentence}</p>
        {v.note && (
          <p className={cn("mt-0.5 text-xs break-words", v.status === "error" ? "text-destructive" : "text-muted-foreground")}>
            {v.note}
          </p>
        )}
        {v.changes.length > 0 && <Changes items={v.changes} />}
        <Technical v={v} />
      </div>
    </li>
  )
}

function Changes({ items }: { items: Change[] }) {
  const [all, setAll] = useState(false)
  const shown = all ? items : items.slice(0, 4)
  return (
    <div className="mt-2 flex flex-col gap-1.5">
      {shown.map((c, i) => (
        <div key={i} className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs">
          <span className="w-full text-[11px] text-muted-foreground sm:w-36 sm:shrink-0 sm:truncate" title={c.field}>
            {fieldName(c.field)}
          </span>
          <span className="max-w-full rounded-md bg-destructive/10 px-1.5 py-0.5 break-all text-muted-foreground line-through decoration-destructive/60">
            {val(c.before)}
          </span>
          <span className="text-muted-foreground">→</span>
          <span className="max-w-full rounded-md bg-success/15 px-1.5 py-0.5 font-medium break-all text-success">{val(c.after)}</span>
          {c.reason && <span className="w-full text-[11px] break-words text-muted-foreground italic sm:pl-38">„{c.reason}”</span>}
        </div>
      ))}
      {items.length > 4 && (
        <button type="button" onClick={() => setAll((a) => !a)} className="self-start text-xs text-primary hover:underline">
          {all ? "Pokaż mniej" : `+${items.length - 4} więcej`}
        </button>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ technical details (collapsed) */

function Technical({ v }: { v: View }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="inline-flex items-center gap-1 text-[11.5px] text-muted-foreground hover:text-foreground"
      >
        <ChevronRight className={cn("size-3 transition-transform", open && "rotate-90")} />
        Szczegóły techniczne
      </button>
      {open && (
        <div className="mt-2 flex min-w-0 flex-col gap-3 rounded-lg border bg-card px-3 py-2.5">
          {v.steps.map((s) => (
            <div key={s.id} className="min-w-0">
              {v.steps.length > 1 && (
                <div className="mb-1 text-xs font-medium">{s.id === "few_shot" ? "Dobór przykładów (few-shot)" : "Wywołanie modelu"}</div>
              )}
              {s.error && <p className="mb-2 font-mono text-[11px] break-all text-destructive">{s.error}</p>}
              <Meta s={s} />
              <StepDetail s={s} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Chip({ children, mono, className }: { children: React.ReactNode; mono?: boolean; className?: string }) {
  return (
    <span className={cn("max-w-full rounded-full bg-muted px-2 py-0.5 text-[11px] break-all text-secondary-foreground", mono && "font-mono", className)}>
      {children}
    </span>
  )
}

function Meta({ s }: { s: Step }) {
  return (
    <div className="mb-2 flex flex-wrap gap-1.5">
      <Chip>czas {sec(s.duration_s)}</Chip>
      {!!s.calls && <Chip>{s.calls}× LLM</Chip>}
      {(s.models || []).map((m) => (
        <Chip key={m} mono>
          {m}
        </Chip>
      ))}
      {s.tokens && (
        <Chip>
          tokeny {s.tokens.prompt} → {s.tokens.completion}
        </Chip>
      )}
      {!!s.cost_usd && <Chip>{usd(s.cost_usd)}</Chip>}
    </div>
  )
}

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
      <div className="mb-1 text-[11px] font-medium text-muted-foreground">{title}</div>
      {children}
    </div>
  )
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-muted-foreground">{children}</p>
}

function JsonBlock({ data, text, label = "JSON" }: { data?: unknown; text?: string; label?: string }) {
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
        <pre className="mt-1 max-h-80 overflow-auto rounded-md bg-muted/60 p-2.5 font-mono text-[11.5px] leading-relaxed break-all whitespace-pre-wrap">
          {text ?? JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  )
}

function DiffRows({ items, empty = "Bez zmian." }: { items?: D[]; empty?: string }) {
  if (!items?.length) return <Empty>{empty}</Empty>
  return (
    <div className="flex flex-col gap-0.5">
      {items.map((c, i) => (
        <div key={i} className="font-mono text-[11px] break-all">
          <span className="text-muted-foreground">{c.field}</span> {val(c.before)} → {val(c.after)}
          {c.rule && <span className="text-muted-foreground"> [{c.rule}]</span>}
        </div>
      ))}
    </div>
  )
}

function LoadDetail({ d }: { d: D }) {
  return (
    <div className="flex flex-col gap-1.5">
      {(d.preprocess || []).length > 0 && (d.ocr_pages || []).length > 0 && (
        <div className="text-xs text-muted-foreground">przygotowanie skanu: {d.preprocess.join(", ")}</div>
      )}
      {d.load_error && <p className="font-mono text-xs break-all text-destructive">{d.load_error}</p>}
      {(d.pages || []).map((p: D) => (
        <div key={p.page} className="rounded-md bg-muted/40 px-2.5 py-2 text-xs">
          <div className="flex flex-wrap items-center gap-1.5">
            <b>str. {p.page}</b>
            <Chip>{p.source === "ocr" ? "OCR" : "tekst z PDF"}</Chip>
            <span className="text-muted-foreground tabular-nums">{p.chars} znaków</span>
            {p.quality != null && <span className="text-muted-foreground">jakość tekstu {p.quality}</span>}
            {p.orientation && (
              <Chip>
                obrót {p.orientation.angle}°{p.orientation.prob ? ` (${pct(p.orientation.prob * 100)})` : ""}
              </Chip>
            )}
            {p.annotation_chars > 0 && <Chip>adnotacje +{p.annotation_chars}</Chip>}
            {p.ocr && (
              <span className="ml-auto text-muted-foreground tabular-nums">
                {p.ocr.model || p.ocr.engine}
                {p.ocr.duration_s != null && ` · ${sec(p.ocr.duration_s)}`}
                {p.ocr.cost_usd ? ` · ${usd(p.ocr.cost_usd)}` : ""}
              </span>
            )}
          </div>
          {p.preview && (
            <pre className="mt-1.5 max-h-28 overflow-auto font-mono text-[11px] leading-snug break-words whitespace-pre-wrap text-secondary-foreground">
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
      <Section title={`Dopasowanie reguł (wymagane co najmniej ${d.min_score ?? "?"})`}>
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
        <Section title="Głosy (reguły + modele)">
          <div className="flex flex-wrap gap-1">
            {d.llm_votes.map((x: string, i: number) => (
              <Chip key={i}>{LABEL[x] || x}</Chip>
            ))}
          </div>
        </Section>
      )}
      {d.method && <p className="mt-1 text-[11px] text-muted-foreground">metoda: {d.method}</p>}
      {d.llm_errors && <p className="mt-1 font-mono text-[11px] break-all text-destructive">{d.llm_errors.join("; ")}</p>}
    </div>
  )
}

function FewShotDetail({ d }: { d: D }) {
  const ex = d.examples || []
  if (!ex.length) return <Empty>Bez przykładów.</Empty>
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
      <p className="mt-1 text-[11px] text-muted-foreground">podobieństwo tekstu · z pamięci dostępnych: {d.learned_available ?? 0}</p>
    </div>
  )
}

function ExtractDetail({ d }: { d: D }) {
  return (
    <div>
      <div className="flex flex-wrap gap-1.5">
        {d.prompt_tokens_est != null && <Chip>prompt ≈ {d.prompt_tokens_est} tok.</Chip>}
        {d.attempts > 1 && <Chip>{d.attempts} próby JSON</Chip>}
        {d.pages_read != null && <Chip>{d.pages_read} str. czytanych</Chip>}
        {d.fill_ratio != null && <Chip>wypełnienie {pct(d.fill_ratio * 100)}</Chip>}
      </div>
      {d.voting && (
        <p className="mt-1 text-xs break-words text-muted-foreground">
          głosowanie: {d.voting.runs} przebiegów · {(d.voting.models || []).join(", ")}
          {d.voting.disagreements?.length ? ` · spory: ${d.voting.disagreements.length}` : ""}
        </p>
      )}
      {d.raw_output && <JsonBlock data={d.raw_output} label="Surowa odpowiedź (JSON)" />}
      {(d.raw_outputs || []).map((r: D, i: number) => (
        <JsonBlock key={i} text={r.raw} label={`Przebieg ${i + 1} · ${r.model || ""}`} />
      ))}
    </div>
  )
}

function NormalizeDetail({ d }: { d: D }) {
  return (
    <div>
      <Section title="normalizacja schematu">
        <DiffRows items={d.normalized} />
      </Section>
      {d.snap_to_text && (
        <Section title="dopasowanie do tekstu (snap_to_text)">
          <DiffRows items={d.snap_to_text} />
        </Section>
      )}
      {d.rules_fill && (
        <Section title="uzupełnienie regułami (rules_fill)">
          <DiffRows items={d.rules_fill} />
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
        <div key={f.field} className="grid grid-cols-[14px_minmax(0,40%)_minmax(0,1fr)] items-baseline gap-x-2 py-0.5 text-xs">
          <span className="self-center">{METHOD_ICON[f.method] || <X className="size-3 text-destructive" />}</span>
          <span className="truncate text-muted-foreground" title={f.field}>
            {fieldName(f.field)}
          </span>
          <span className="truncate">
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
      {!rounds.length && <Empty>Brak uwag.</Empty>}
      {rounds.map((r, i) => (
        <Section key={i} title={`runda ${i + 1}: uwagi`}>
          {(r.issues || []).map((x: D, j: number) => (
            <div key={j} className="text-xs break-words">
              <span className="text-muted-foreground">{fieldName(x.field)}</span> = {val(x.value)} · {x.issue}
            </div>
          ))}
          {r.error && <p className="font-mono text-[11px] break-all text-destructive">{r.error}</p>}
        </Section>
      ))}
      {(d.remaining_issues || []).length > 0 && (
        <Section title="pozostałe uwagi">
          {d.remaining_issues.map((x: D, j: number) => (
            <div key={j} className="text-xs break-words">
              <span className="text-muted-foreground">{fieldName(x.field)}</span> · {x.issue}
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
      <Section title="sygnały trudności">
        {(d.reasons || []).length ? (
          <ul className="flex flex-col gap-0.5 text-xs">
            {d.reasons.map((r: string) => (
              <li key={r}>• {r}</li>
            ))}
          </ul>
        ) : (
          <Empty>Brak.</Empty>
        )}
        {(d.disputed || []).length > 0 && (
          <p className="mt-1 text-[11px] break-words text-muted-foreground">rozbieżne pola: {d.disputed.map(fieldName).join(", ")}</p>
        )}
      </Section>
      {d.vote && (
        <Section title="kaskada">
          {(d.vote.steps || []).map((s: D) => (
            <div key={s.level} className="text-xs break-words">
              poziom {s.level}: <span className="font-mono text-[11px]">{s.models.join(" + ")}</span>
              {s.disagreed_with_previous?.length ? ` · różnice: ${s.disagreed_with_previous.length}` : " · potwierdził"}
            </div>
          ))}
          <div className="text-[11px] text-muted-foreground">głosujących: {d.vote.voters}</div>
        </Section>
      )}
    </div>
  )
}
