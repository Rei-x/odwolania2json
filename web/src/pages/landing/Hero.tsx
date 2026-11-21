import { lazy, Suspense, useRef, useState, type DragEvent, type Ref } from "react"
import { useNavigate } from "react-router-dom"
import { Flock } from "@/components/brand/flock"
import { SparrowMark } from "@/components/brand/logo"

const HeroScene = lazy(() => import("./HeroScene"))

const isPdf = (f: File) => f.type === "application/pdf" || /\.pdf$/i.test(f.name)

/** Primary action: drop or pick the case PDFs; the workbench (/app) picks them up from router state. */
function DropZone() {
  const navigate = useNavigate()
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const [error, setError] = useState("")
  const send = (list: FileList | null) => {
    const files = Array.from(list ?? []).filter(isPdf)
    if (!files.length) { setError("Tylko pliki PDF."); return }
    navigate("/app", { state: { files } })
  }
  const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); send(e.dataTransfer.files) }
  return (
    <div
      className={over ? "drop over" : "drop"}
      role="button"
      tabIndex={0}
      aria-label="Upuść PDF-y sprawy albo wybierz pliki"
      onClick={() => input.current?.click()}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.current?.click() } }}
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 16V4M7 9l5-5 5 5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
      </svg>
      <span className="drop-t">Upuść PDF-y sprawy</span>
      <span className="drop-s">{error || "albo wybierz pliki (.pdf)"}</span>
      <input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden onChange={(e) => send(e.target.files)} />
    </div>
  )
}

export function Hero({ ref }: { ref?: Ref<HTMLElement> }) {
  return (
    <section className="hero" id="hero" ref={ref}>
      <div className="hcopy">
        <h1>
          <span className="l l1"><SparrowMark className="hero-mark" />Wróbelek</span>
          <span className="l l3">opus-like quality for pennies</span>
        </h1>
        <p className="lede">Akta KIO → JSON zgodny ze schematem UZP, każda wartość ze stroną i cytatem.</p>
        <DropZone />
      </div>
      <div className="hscene">
        <Flock />
        <Suspense fallback={null}>
          <HeroScene />
        </Suspense>
      </div>
    </section>
  )
}
