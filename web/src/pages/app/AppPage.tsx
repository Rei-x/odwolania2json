import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom"
import { BarChart3, Download, FileUp, Plus } from "lucide-react"
import { toast } from "sonner"
import { Flock } from "@/components/brand/flock"
import { SiteNav } from "@/components/brand/site-nav"
import { Button, buttonVariants } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { DocStrip } from "./doc-strip"
import { api, type Sample } from "./lib"
import { MemoryButton, ModelPicker, ProfileControl, SamplesMenu } from "./controls"
import { PdfPreview } from "./pdf-preview"
import { evMap, ResultPanel, type View } from "./result-panel"
import { useWorkbench } from "./use-workbench"

const LS_SPLIT = "o2j.split"

export default function AppPage() {
  const wb = useWorkbench()
  const { docs, cur, add, setCurId } = wb
  const fileInput = useRef<HTMLInputElement>(null)
  const [view, setView] = useState<View>("dane")
  const [selected, setSelected] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)

  const pick = useCallback(
    (id: number) => {
      setCurId(id)
      setSelected(null)
    },
    [setCurId],
  )

  const loadSample = useCallback(
    (s: Sample) => {
      Promise.all((s.files || [s.name]).map(api.sampleFile))
        .then(add)
        .catch((e: Error) => toast.error("Nie udało się wczytać przykładu: " + e.message))
    },
    [add],
  )

  // ?sample=<name> (links from the landing page)
  const [params, setParams] = useSearchParams()
  useEffect(() => {
    const name = params.get("sample")
    if (!name) return
    setParams({}, { replace: true })
    api
      .samples()
      .then((l) => {
        const s = l.find((x) => x.name === name)
        if (s) loadSample(s)
      })
      .catch(() => {})
  }, [params, setParams, loadSample])

  // files handed over by the wizard (/nowy-typ: "Przetwórz <plik> w aplikacji")
  const location = useLocation()
  const navigate = useNavigate()
  const handedOver = useRef<unknown>(null)
  useEffect(() => {
    const files = (location.state as { files?: unknown } | null)?.files
    if (!Array.isArray(files) || !files.length || handedOver.current === files) return
    handedOver.current = files // StrictMode runs effects twice; add each hand-over once
    add(files.filter((f): f is File => f instanceof File))
    navigate(".", { replace: true, state: null })
  }, [location.state, add, navigate])

  // drag & drop anywhere on the page
  useEffect(() => {
    let n = 0
    const enter = (e: DragEvent) => {
      if (!e.dataTransfer?.types.includes("Files")) return
      e.preventDefault()
      n++
      setDragging(true)
    }
    const leave = () => {
      if (--n <= 0) {
        n = 0
        setDragging(false)
      }
    }
    const over = (e: DragEvent) => e.preventDefault()
    const drop = (e: DragEvent) => {
      e.preventDefault()
      n = 0
      setDragging(false)
      add([...(e.dataTransfer?.files || [])].filter((f) => /\.pdf$/i.test(f.name)))
    }
    window.addEventListener("dragenter", enter)
    window.addEventListener("dragleave", leave)
    window.addEventListener("dragover", over)
    window.addEventListener("drop", drop)
    return () => {
      window.removeEventListener("dragenter", enter)
      window.removeEventListener("dragleave", leave)
      window.removeEventListener("dragover", over)
      window.removeEventListener("drop", drop)
    }
  }, [add])

  // ← / → switch documents
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!docs.length || !cur) return
      const t = e.target as HTMLElement
      if (t.closest("input, textarea, [role=slider], [role=dialog], [data-slot=popover-content]")) return
      const i = docs.findIndex((d) => d.id === cur.id)
      if (e.key === "ArrowRight" && i < docs.length - 1) pick(docs[i + 1].id)
      if (e.key === "ArrowLeft" && i > 0) pick(docs[i - 1].id)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [docs, cur, pick])

  const openPicker = () => fileInput.current?.click()
  const download = () => {
    if (!cur || cur.pending) return
    const a = document.createElement("a")
    a.href = URL.createObjectURL(new Blob([JSON.stringify(cur.result, null, 2)], { type: "application/json" }))
    a.download = cur.file.replace(/\.pdf$/i, ".json")
    a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 1000)
  }

  const evidence = useMemo(() => (selected ? evMap(cur)[selected] ?? null : null), [cur, selected])
  // re-run the case cross-check whenever a document finishes or gets approved
  const caseKey = docs.map((d) => `${d.id}:${d.pending ? 0 : 1}:${d.approved ? 1 : 0}`).join(",")

  const profileControls = (
    <>
      <ProfileControl
        profiles={wb.profiles}
        profile={wb.profile}
        setProfile={wb.setProfile}
        models={wb.models}
        override={wb.model}
      />
      <ModelPicker
        models={wb.models}
        model={wb.model}
        setModel={wb.setModel}
        profile={wb.profile}
        onOpen={wb.loadModels}
      />
    </>
  )

  return (
    <div className="flex min-h-svh flex-col bg-background lg:h-svh lg:min-h-0">
      <input
        ref={fileInput}
        type="file"
        accept=".pdf"
        multiple
        hidden
        onChange={(e) => {
          add([...(e.target.files || [])])
          e.target.value = ""
        }}
      />
      <SiteNav>
        <SamplesMenu onPick={loadSample} />
        <Button size="sm" className="rounded-full" onClick={openPicker}>
          <Plus /> <span className="hidden sm:inline">Dodaj PDF</span>
        </Button>
      </SiteNav>

      {!docs.length ? (
        <EmptyState
          dragging={dragging}
          onPick={openPicker}
          onSample={loadSample}
          controls={profileControls}
        />
      ) : (
        <>
          <div className="mx-auto flex w-full max-w-[1400px] flex-wrap items-center gap-x-3 gap-y-2 px-4 pt-3 pb-2">
            <div className="order-2 flex w-full min-w-0 lg:order-1 lg:w-auto lg:flex-1">
              <DocStrip docs={docs} curId={cur?.id ?? null} onPick={pick} />
            </div>
            <div className="order-1 flex min-w-0 shrink-0 flex-wrap items-center gap-2 max-lg:w-full lg:order-2 lg:flex-nowrap">
              {profileControls}
              <MemoryButton stats={wb.stats} />
              <Button
                variant="outline"
                size="icon"
                className="size-9 shrink-0 rounded-full"
                title="Pobierz JSON"
                aria-label="Pobierz JSON"
                disabled={!cur || cur.pending}
                onClick={download}
              >
                <Download />
              </Button>
            </div>
          </div>
          {cur && (
            <Workspace
              left={<PdfPreview doc={cur} evidence={evidence} />}
              right={
                <ResultPanel
                  doc={cur}
                  view={view}
                  setView={setView}
                  selected={selected}
                  onSelect={setSelected}
                  onEdit={(p, v) => wb.editField(cur.id, p, v)}
                  onApprove={() => wb.approve(cur)}
                  saving={wb.savingIds.includes(cur.id)}
                  models={wb.models}
                  caseId={wb.caseId}
                  caseKey={caseKey}
                />
              }
            />
          )}
        </>
      )}

      {dragging && docs.length > 0 && (
        <div className="pointer-events-none fixed inset-2.5 z-50 grid place-items-center rounded-3xl border-[3px] border-dashed border-primary bg-primary/5 text-xl font-bold text-primary">
          Upuść, aby dodać
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ split view */

function Workspace({ left, right }: { left: React.ReactNode; right: React.ReactNode }) {
  const box = useRef<HTMLDivElement>(null)
  const [split, setSplit] = useState(() => {
    try {
      const v = Number(localStorage.getItem(LS_SPLIT))
      return v >= 25 && v <= 75 ? v : 50
    } catch {
      return 50
    }
  })
  const [drag, setDrag] = useState(false)
  const save = (v: number) => {
    try {
      localStorage.setItem(LS_SPLIT, String(v))
    } catch {
      /* ignore */
    }
  }
  return (
    <main
      ref={box}
      className={cn(
        "mx-auto flex w-full max-w-[1400px] flex-col gap-3 px-4 pb-4 lg:grid lg:min-h-0 lg:flex-1 lg:gap-0",
        drag && "cursor-col-resize select-none",
      )}
      style={{ gridTemplateColumns: `minmax(0,${split}fr) 14px minmax(0,${100 - split}fr)` }}
    >
      <section className="h-[55svh] min-h-0 lg:h-auto">{left}</section>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-valuenow={Math.round(split)}
        aria-valuemin={25}
        aria-valuemax={75}
        tabIndex={0}
        title="Przeciągnij, aby zmienić proporcje (dwuklik: po równo)"
        className="group hidden cursor-col-resize items-center justify-center outline-none lg:flex"
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId)
          setDrag(true)
        }}
        onPointerMove={(e) => {
          if (!drag || !box.current) return
          const r = box.current.getBoundingClientRect()
          const v = Math.min(75, Math.max(25, ((e.clientX - r.left - 16) / (r.width - 32)) * 100))
          setSplit(v)
        }}
        onPointerUp={() => {
          setDrag(false)
          save(split)
        }}
        onDoubleClick={() => {
          setSplit(50)
          save(50)
        }}
        onKeyDown={(e) => {
          const d = e.key === "ArrowLeft" ? -2 : e.key === "ArrowRight" ? 2 : 0
          if (!d) return
          e.preventDefault()
          e.stopPropagation()
          const v = Math.min(75, Math.max(25, split + d))
          setSplit(v)
          save(v)
        }}
      >
        <span
          className={cn(
            "h-10 w-1 rounded-full bg-border transition-colors group-hover:bg-primary/50 group-focus-visible:bg-primary",
            drag && "bg-primary",
          )}
        />
      </div>
      <section className="min-h-0 lg:h-auto">{right}</section>
    </main>
  )
}

/* ------------------------------------------------------------------ empty state */

function EmptyState({
  dragging,
  onPick,
  onSample,
  controls,
}: {
  dragging: boolean
  onPick: () => void
  onSample: (s: Sample) => void
  controls: React.ReactNode
}) {
  return (
    <div className="relative flex flex-1 items-center justify-center overflow-hidden px-4 py-10">
      <Flock className="opacity-60" />
      <div className="relative z-10 flex w-full max-w-xl flex-col items-center gap-6">
        <button
          type="button"
          onClick={onPick}
          className={cn(
            "group grid aspect-[16/10] w-full place-items-center rounded-3xl border-[1.5px] border-dashed border-input bg-card/80 shadow-sm backdrop-blur transition-all hover:-translate-y-0.5 hover:border-primary hover:shadow-lg hover:shadow-primary/10",
            dragging && "-translate-y-0.5 border-primary bg-accent/60 shadow-lg shadow-primary/10",
          )}
        >
          <span className="flex flex-col items-center gap-3 px-6 text-center">
            <span className="grid size-16 place-items-center rounded-2xl bg-primary text-primary-foreground shadow-md shadow-primary/20 transition-transform group-hover:scale-105">
              <FileUp className="size-7" />
            </span>
            <b className="text-lg">{dragging ? "Upuść, aby dodać" : "Upuść PDF-y sprawy"}</b>
            <small className="text-sm text-muted-foreground">lub kliknij, aby wybrać pliki</small>
          </span>
        </button>
        <div className="flex flex-wrap items-center justify-center gap-2">
          {[
            ["odwołanie", "bg-primary"],
            ["pełnomocnictwo", "bg-sage"],
            ["przelew", "bg-wheat"],
          ].map(([t, c]) => (
            <span
              key={t}
              className="inline-flex items-center gap-1.5 rounded-full border bg-card px-3 py-1 text-xs text-secondary-foreground"
            >
              <span className={cn("size-2 rounded-full", c)} />
              {t}
            </span>
          ))}
          <SamplesMenu onPick={onSample} className="border bg-card" alwaysLabel />
        </div>
        <div className="flex flex-wrap items-center justify-center gap-2">{controls}</div>
        <div className="flex flex-wrap items-center justify-center gap-1 text-sm">
          <Link to="/nowy-typ" className={buttonVariants({ variant: "link", size: "sm" })}>
            <Plus /> Nowy typ dokumentu
          </Link>
          <Link to="/benchmarks" className={cn(buttonVariants({ variant: "link", size: "sm" }), "text-muted-foreground")}>
            <BarChart3 /> Benchmarki
          </Link>
        </div>
      </div>
    </div>
  )
}
