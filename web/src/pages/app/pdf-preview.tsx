import { useEffect, useRef, useState } from "react"
import { Skeleton } from "@/components/ui/skeleton"
import { api, type Doc, type Evidence } from "./lib"

/** Rendered PDF pages (PNG from /api/page) with the selected field's evidence boxed on its page. */
export function PdfPreview({ doc, evidence }: { doc: Doc | null; evidence: Evidence | null }) {
  const scroller = useRef<HTMLDivElement>(null)
  const pageRefs = useRef<Record<number, HTMLDivElement | null>>({})
  // natural aspect ratio per page, so lazy images do not shift offsets used for scrolling to evidence
  const [ratios, setRatios] = useState<Record<number, number>>({})

  const key = doc ? `${doc.session}/${doc.file}` : ""
  useEffect(() => {
    setRatios({})
    scroller.current?.scrollTo({ top: 0 })
  }, [key])

  useEffect(() => {
    const el = scroller.current
    if (!el || !evidence?.page) return
    const pg = pageRefs.current[evidence.page]
    if (!pg) return
    const first = evidence.rects?.[0]
    const y = pg.offsetTop + (first ? (first[1] / 100) * pg.offsetHeight - el.clientHeight / 3 : 0)
    // on narrow screens the preview sits above the fields: bring it into view first (instantly, so the two
    // scrolls do not cancel each other), then scroll the pages to the evidence
    if (window.matchMedia("(max-width: 1023px)").matches) el.scrollIntoView({ block: "nearest" })
    el.scrollTo({ top: Math.max(0, y), behavior: "smooth" })
  }, [evidence])

  const ready = doc && !doc.pending && doc.session
  const n = (ready && doc.trace?.pages) || 1

  return (
    <div
      ref={scroller}
      className="relative h-full min-h-0 scroll-mt-16 overflow-y-auto overscroll-contain rounded-2xl bg-muted/50 p-3 sm:p-4"
    >
      {!ready ? (
        <div className="mx-auto max-w-[760px]">
          <Skeleton className="aspect-[1/1.414] w-full rounded-lg bg-card" />
        </div>
      ) : (
        Array.from({ length: n }, (_, k) => {
          const p = k + 1
          const hl = evidence?.page === p ? evidence.rects || [] : []
          return (
            <div
              key={`${key}/${p}`}
              ref={(r) => {
                pageRefs.current[p] = r
              }}
              className="relative mx-auto mb-4 max-w-[760px] overflow-hidden rounded-lg bg-white shadow-sm ring-1 ring-foreground/5 last:mb-0"
              style={{ aspectRatio: ratios[p] ?? 1 / 1.414 }}
            >
              <img
                loading="lazy"
                alt={`Strona ${p}`}
                src={api.pageUrl(doc.session!, doc.file, p)}
                className="block h-full w-full"
                onLoad={(e) => {
                  const im = e.currentTarget
                  if (im.naturalWidth) {
                    const r = im.naturalWidth / im.naturalHeight
                    setRatios((rs) => (rs[p] === r ? rs : { ...rs, [p]: r }))
                  }
                }}
              />
              {hl.map(([x, y, w, h], i) => (
                <div
                  key={`${evidence?.field}-${i}`}
                  className="pointer-events-none absolute animate-in rounded-[3px] bg-primary/15 outline-2 outline-offset-1 outline-primary/85 duration-300 fade-in zoom-in-125"
                  style={{ left: `${x}%`, top: `${y}%`, width: `${w}%`, height: `${h}%` }}
                />
              ))}
              <span className="absolute right-2.5 bottom-2 rounded bg-white/80 px-1 text-[11px] text-muted-foreground tabular-nums">
                {p}/{n}
              </span>
            </div>
          )
        })
      )}
    </div>
  )
}
