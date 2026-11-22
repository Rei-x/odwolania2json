import { Fragment, useEffect, useRef, useState } from "react"
import { Check, Clock, Cpu, FileText, Pencil, ScanLine, Wrench } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"
import { fmtSec } from "@/lib/format"
import { displayValue, fieldLabel, pathLabel, prettyModel, sectionLabel, useDoctypeLabels, useEnumLabels } from "@/lib/labels"
import { TraceView } from "./trace-view"
import {
  api,
  type CaseReport,
  type Doc,
  type Evidence,
  getP,
  type Json,
  type JsonObj,
  LABEL,
  METHOD_DOT,
  METHOD_LABEL,
  type Model,
  parseEdit,
  pb,
  PNAME,
  typeDot,
} from "./lib"

export type View = "dane" | "json" | "sprawa" | "przebieg"

type Props = {
  doc: Doc
  view: View
  setView: (v: View) => void
  selected: string | null
  onSelect: (path: string | null) => void
  onEdit: (path: string, val: Json) => void
  onApprove: () => void
  saving?: boolean
  models: Model[]
  caseId: string | null
  caseKey: string
}

export function evMap(d: Doc | null): Record<string, Evidence> {
  const m: Record<string, Evidence> = {}
  ;(d?.trace?.evidence || []).forEach((e) => (m[e.field] = e))
  return m
}

export function ResultPanel(p: Props) {
  const { doc: d } = p
  const docLabel = useDoctypeLabels()
  if (d.pending) return <PendingPanel />
  const t = d.trace || {}
  const fixes = (t.verification?.rounds || []).flatMap((r) => r.changes || [])
  const canApprove = d.doctype && d.doctype in LABEL && d.doctype !== "error" && d.doctype !== "inny"
  const data = d.edited || d.result || {}
  return (
    <Tabs
      value={p.view}
      onValueChange={(v) => p.setView(v as View)}
      className="flex h-full min-h-0 flex-col gap-0 overflow-hidden rounded-2xl border bg-card shadow-sm"
    >
      <div className="flex flex-col gap-2.5 border-b px-4 pt-3.5 pb-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className={cn("size-2.5 shrink-0 rounded-full", typeDot(d.doctype))} />
          <h2 className="text-xl font-semibold tracking-tight">{docLabel(d.doctype)}</h2>
          <div className="ml-auto flex max-w-full flex-wrap items-center justify-end gap-2">
            <TabsList>
              <TabsTrigger value="dane" className="px-2.5">
                Dane
              </TabsTrigger>
              <TabsTrigger value="json" className="px-2.5">
                JSON
              </TabsTrigger>
              <TabsTrigger value="sprawa" className="px-2.5">
                Sprawa
              </TabsTrigger>
              <TabsTrigger value="przebieg" className="px-2.5">
                Przebieg
              </TabsTrigger>
            </TabsList>
            {canApprove && (
              <Button
                size="sm"
                variant={d.edited ? "default" : d.approved ? "outline" : "secondary"}
                className={cn("h-8 rounded-full px-3", !d.edited && !d.approved && "bg-foreground text-background hover:bg-foreground/85")}
                onClick={p.onApprove}
                disabled={p.saving}
                title="Zapisz do pamięci systemu"
              >
                {d.approved && !d.edited && <Check />}
                {d.edited ? "Zapisz poprawki" : d.approved ? "Zatwierdzono" : "Zatwierdź"}
              </Button>
            )}
          </div>
        </div>
        <Chips doc={d} models={p.models} fixes={fixes.length} />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 pt-1 pb-4">
        {p.view === "przebieg" ? (
          <TraceView doc={d} />
        ) : d.error ? (
          <p className="p-4 text-sm break-words text-destructive">{d.error}</p>
        ) : p.view === "sprawa" ? (
          <CaseView caseId={p.caseId} caseKey={p.caseKey} />
        ) : p.view === "json" ? (
          <pre className="px-3 py-3 font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap">
            <HJson x={data} ind={0} />
          </pre>
        ) : (
          <>
            {fixes.length > 0 && (
              <div className="mx-2 mt-2 mb-1 rounded-lg bg-sage/10 px-3 py-2 text-xs text-foreground">
                <b>Weryfikacja poprawiła:</b>
                {fixes.map((f, i) => (
                  <div key={i} className="mt-0.5 break-words">
                    {pathLabel(f.field)}: <s className="text-muted-foreground">{JSON.stringify(f.before)}</s> →{" "}
                    {JSON.stringify(f.after)}
                  </div>
                ))}
              </div>
            )}
            <Fields {...p} obj={data} path="" ev={evMap(d)} />
          </>
        )}
      </div>
    </Tabs>
  )
}

function PendingPanel() {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border bg-card shadow-sm">
      <div className="flex flex-col gap-2.5 border-b px-4 pt-4 pb-3">
        <Skeleton className="h-6 w-1/2" />
        <Skeleton className="h-4 w-3/4" />
      </div>
      <div className="flex flex-col gap-3 p-4">
        {Array.from({ length: 9 }, (_, i) => (
          <div key={i} className="grid grid-cols-[38%_1fr] gap-3">
            <Skeleton className="h-3.5" />
            <Skeleton className="h-3.5" />
          </div>
        ))}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ chips (run metadata) */

function Chip({ children, className, title }: { children: React.ReactNode; className?: string; title?: string }) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs whitespace-nowrap text-secondary-foreground [&_svg]:size-3",
        className,
      )}
    >
      {children}
    </span>
  )
}

function Chips({ doc, models, fixes }: { doc: Doc; models: Model[]; fixes: number }) {
  const t = doc.trace || {}
  const ov = t.model_override
  const ovm = ov ? models.find((x) => x.id === ov) : undefined
  return (
    <div className="flex flex-wrap gap-1.5">
      {!!t.pages && (
        <Chip>
          <FileText /> {t.pages} str.
        </Chip>
      )}
      {!!t.elapsed_s && (
        <Chip>
          <Clock /> {fmtSec(t.elapsed_s)}
        </Chip>
      )}
      {!!t.ocr_pages?.length && (
        <Chip>
          <ScanLine /> OCR
        </Chip>
      )}
      {fixes > 0 && (
        <Chip>
          <Wrench /> {fixes} popr.
        </Chip>
      )}
      {t.active_profile && (
        <Chip>
          <Check /> {PNAME[t.active_profile] || t.active_profile}
        </Chip>
      )}
      {ov ? (
        <Chip
          className={ovm && !ovm.eu ? "bg-wheat/30 text-bark" : "bg-foreground text-background"}
          title={`Model wybrany ręcznie: ${ov} (OCR + klasyfikacja + ekstrakcja)${ovm && !ovm.eu ? ", poza UE, tylko eksperyment" : ""}`}
        >
          <Cpu /> model: {prettyModel(t.model || ov)}
          {ovm && ` · ${pb(ovm.params_b)}`}
          {ovm && !ovm.eu && " · poza UE"}
        </Chip>
      ) : t.voting?.models ? (
        <Chip>
          <Cpu /> głosowanie: {t.voting.models.map(prettyModel).join(" + ")}
        </Chip>
      ) : t.model ? (
        <Chip>
          <Cpu /> {prettyModel(t.model)}
        </Chip>
      ) : null}
      {t.ocr_model && t.ocr_model !== t.model && (
        <Chip>
          <ScanLine /> OCR: {prettyModel(t.ocr_model)}
        </Chip>
      )}
      {t.router &&
        (t.router.escalate ? (
          <Chip>
            <ScanLine /> eskalacja →{" "}
            {(t.router.vote?.steps || []).map((s) => s.models.map(prettyModel).join(" + ")).join(" → ")}
          </Chip>
        ) : (
          <Chip>
            <ScanLine /> łatwy dokument, bez eskalacji
          </Chip>
        ))}
    </div>
  )
}

/* ------------------------------------------------------------------ fields */

type FieldsProps = Props & { obj: JsonObj; path: string; ev: Record<string, Evidence>; depth?: number }

function SectionLabel({ children, sub }: { children: React.ReactNode; sub?: boolean }) {
  return sub ? (
    <div className="mx-3 mt-2 text-xs text-muted-foreground">{children}</div>
  ) : (
    <div className="mx-3 mt-4 mb-1 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
      {children}
    </div>
  )
}

function Fields(fp: FieldsProps) {
  const { obj, path, depth = 0 } = fp
  return (
    <>
      {Object.entries(obj || {}).map(([k, v]) => {
        const p = path ? `${path}.${k}` : k
        if (Array.isArray(v)) {
          if (!v.length)
            return (
              <Fragment key={p}>
                <SectionLabel>{sectionLabel(k)}</SectionLabel>
                <div className="grid grid-cols-[minmax(110px,38%)_1fr] gap-3 px-3 py-1.5 text-sm">
                  <span className="text-muted-foreground">—</span>
                  <span className="text-muted-foreground/60">brak</span>
                </div>
              </Fragment>
            )
          return (
            <Fragment key={p}>
              {v.map((it, i) => (
                <Fragment key={i}>
                  <SectionLabel>
                    {sectionLabel(k)}
                    {v.length > 1 ? ` ${i + 1}` : ""}
                  </SectionLabel>
                  {it && typeof it === "object" && !Array.isArray(it) ? (
                    <Fields {...fp} obj={it} path={`${p}[${i}]`} depth={depth + 1} />
                  ) : (
                    <Row {...fp} p={`${p}[${i}]`} k={k} v={it} />
                  )}
                </Fragment>
              ))}
            </Fragment>
          )
        }
        if (v && typeof v === "object")
          return (
            <Fragment key={p}>
              <SectionLabel sub={depth > 0}>{depth > 0 ? fieldLabel(k) : sectionLabel(k)}</SectionLabel>
              <Fields {...fp} obj={v} path={p} depth={depth + 1} />
            </Fragment>
          )
        return <Row key={p} {...fp} p={p} k={k} v={v} />
      })}
    </>
  )
}

function Row({ doc, ev, selected, onSelect, onEdit, p, k, v }: FieldsProps & { p: string; k: string; v: Json }) {
  const e = ev[p]
  const on = selected === p
  const [editing, setEditing] = useState(false)
  const edited =
    !!doc.edited && JSON.stringify(getP(doc.edited, p)) !== JSON.stringify(getP(doc.result, p))
  const enums = useEnumLabels(doc.doctype)
  const display = displayValue(k, v, enums)
  return (
    <div
      data-p={p}
      role="button"
      tabIndex={0}
      title="Kliknij, aby zobaczyć źródło; dwukrotnie, aby poprawić"
      onClick={() => !editing && onSelect(on ? null : p)}
      onDoubleClick={() => setEditing(true)}
      onKeyDown={(ev) => {
        if (editing) return
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault()
          onSelect(on ? null : p)
        }
      }}
      className={cn(
        "group grid cursor-pointer grid-cols-[minmax(110px,38%)_1fr_auto] items-baseline gap-x-3 rounded-lg px-3 py-1.5 transition-colors outline-none hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring/50",
        on && "bg-accent hover:bg-accent",
      )}
    >
      <span className="text-[13px] text-muted-foreground">{fieldLabel(k)}</span>
      {editing ? (
        <EditInput
          initial={v === null ? "" : String(v)}
          onDone={(raw) => {
            setEditing(false)
            if (raw !== null) onEdit(p, parseEdit(raw))
          }}
        />
      ) : (
        <span
          className={cn(
            "text-sm font-semibold break-words",
            v === null && "font-normal text-muted-foreground/50",
            edited && "text-primary",
          )}
        >
          {display}
        </span>
      )}
      <span className="flex items-center gap-1.5 self-center">
        <button
          type="button"
          aria-label="Popraw wartość"
          onClick={(ev) => {
            ev.stopPropagation()
            setEditing(true)
          }}
          className="rounded p-0.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-foreground focus-visible:opacity-100 max-lg:opacity-60"
        >
          <Pencil className="size-3" />
        </button>
        <span
          title={e ? METHOD_LABEL[e.method] || e.method : undefined}
          className={cn("size-[7px] rounded-full", e ? METHOD_DOT[e.method] || "bg-muted-foreground" : "opacity-0")}
        />
      </span>
      {on && (
        <div
          onClick={(ev) => ev.stopPropagation()}
          className="col-span-full mt-1.5 cursor-text rounded-md bg-background/70 px-2.5 py-2 text-xs text-secondary-foreground"
        >
          <EvidenceText e={e} />
        </div>
      )}
    </div>
  )
}

function EditInput({ initial, onDone }: { initial: string; onDone: (v: string | null) => void }) {
  const [val, setVal] = useState(initial)
  const done = useRef(false)
  const finish = (v: string | null) => {
    if (done.current) return
    done.current = true
    onDone(v)
  }
  return (
    <input
      autoFocus
      value={val}
      onFocus={(e) => e.currentTarget.select()}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => setVal(e.target.value)}
      onKeyDown={(e) => {
        e.stopPropagation()
        if (e.key === "Enter") finish(val)
        if (e.key === "Escape") finish(null)
      }}
      onBlur={() => finish(val)}
      className="w-full min-w-0 rounded-md border border-primary bg-background px-1.5 py-0.5 text-sm font-semibold outline-none"
    />
  )
}

function EvidenceText({ e }: { e?: Evidence }) {
  if (!e) return <>Brak w dokumencie.</>
  if (e.method === "derived") return <>Wyznaczone regułą z konfiguracji.</>
  if (e.method === "inferred") return <>Wywnioskowane przez model (brak dosłownego cytatu).</>
  const q = e.quote || ""
  const c = e.context || q
  const i = q ? c.indexOf(q) : -1
  return (
    <>
      <span className="font-medium">str. {e.page}</span> · „…
      {i < 0 ? (
        c
      ) : (
        <>
          {c.slice(0, i)}
          <mark className="rounded-sm bg-primary/20 px-0.5 text-foreground">{q}</mark>
          {c.slice(i + q.length)}
        </>
      )}
      …”
    </>
  )
}

/* ------------------------------------------------------------------ JSON view */

function HJson({ x, ind }: { x: Json; ind: number }): React.ReactNode {
  const pad = "  ".repeat(ind)
  if (x === null) return <span className="text-muted-foreground/60">null</span>
  if (typeof x === "number" || typeof x === "boolean") return <span className="text-primary">{String(x)}</span>
  if (typeof x === "string") return <span className="text-sage">"{x}"</span>
  if (Array.isArray(x))
    return x.length ? (
      <>
        {"[\n"}
        {x.map((v, i) => (
          <Fragment key={i}>
            {pad + "  "}
            <HJson x={v} ind={ind + 1} />
            {i < x.length - 1 ? ",\n" : "\n"}
          </Fragment>
        ))}
        {pad + "]"}
      </>
    ) : (
      "[]"
    )
  const ents = Object.entries(x)
  return (
    <>
      {"{\n"}
      {ents.map(([k, v], i) => (
        <Fragment key={k}>
          {pad + "  "}
          <span className="text-accent-foreground">"{k}"</span>: <HJson x={v} ind={ind + 1} />
          {i < ents.length - 1 ? ",\n" : "\n"}
        </Fragment>
      ))}
      {pad + "}"}
    </>
  )
}

/* ------------------------------------------------------------------ case cross-check */

function CaseView({ caseId, caseKey }: { caseId: string | null; caseKey: string }) {
  const [rep, setRep] = useState<CaseReport | null>(null)
  const [err, setErr] = useState(false)
  useEffect(() => {
    if (!caseId) return
    let live = true
    setErr(false)
    api
      .caseReport(caseId)
      .then((r) => live && setRep(r))
      .catch(() => live && setErr(true))
    return () => {
      live = false
    }
  }, [caseId, caseKey])
  if (err) return <p className="p-4 text-sm text-muted-foreground">Nie udało się przeanalizować sprawy.</p>
  if (!rep) return <p className="p-4 text-sm text-muted-foreground">Analiza spójności sprawy…</p>
  const icon: Record<string, string> = { ok: "✓", uwaga: "!", "n/d": "–" }
  const color: Record<string, string> = { ok: "text-success", uwaga: "text-primary", "n/d": "text-muted-foreground/60" }
  const docs = Object.entries(rep.dokumenty || {})
  return (
    <div className="flex flex-col gap-0.5 px-1 py-2">
      <div className="mx-2 mb-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        Dokumenty sprawy:
        {docs.length
          ? docs.map(([f, t]) => (
              <span key={f} className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-foreground">
                <span className={cn("size-1.5 rounded-full", typeDot(t))} />
                {f}
              </span>
            ))
          : " brak"}
      </div>
      {(rep.kontrole || []).map((c, i) => (
        <div key={i} className="grid grid-cols-[22px_1fr] items-start gap-2 rounded-lg px-3 py-2 odd:bg-muted/40">
          <span className={cn("font-bold", color[c.status] || "")}>{icon[c.status] || "?"}</span>
          <div className="text-sm">
            {c.opis}
            <small className="block text-xs break-all text-muted-foreground">{c.szczegoly}</small>
          </div>
        </div>
      ))}
      {!rep.kontrole?.length && <p className="px-3 text-sm text-muted-foreground">Brak kontroli do wykonania.</p>}
      {!!rep.uzupelnienia_krzyzowe?.length && (
        <div className="mx-2 mt-2 rounded-lg bg-sage/10 px-3 py-2 text-xs">
          <b>Uzupełniono krzyżowo:</b>
          {rep.uzupelnienia_krzyzowe.map((f, i) => (
            <div key={i} className="mt-0.5">
              {f.dokument} · {pathLabel(f.pole)} = {String(f.wartosc)} (z {f.zrodlo})
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
