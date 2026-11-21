import { useEffect, useRef } from "react"
import { ListIcon, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"
import { type Doc, LABEL, typeDot } from "./lib"

const stem = (f: string) => f.replace(/\.pdf$/i, "")

/**
 * Case documents as a horizontally scrolling strip. It always takes the remaining width (min-w-0) and never wraps,
 * so a case with dozens of files cannot push the controls or the panes around; with many files a list popover
 * gives direct access to all of them.
 */
export function DocStrip({ docs, curId, onPick }: { docs: Doc[]; curId: number | null; onPick: (id: number) => void }) {
  const strip = useRef<HTMLDivElement>(null)

  useEffect(() => {
    strip.current?.querySelector<HTMLElement>("[data-on=true]")?.scrollIntoView({ block: "nearest", inline: "nearest" })
  }, [curId, docs.length])

  // vertical wheel scrolls the strip sideways
  useEffect(() => {
    const el = strip.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && el.scrollWidth > el.clientWidth) {
        el.scrollLeft += e.deltaY
        e.preventDefault()
      }
    }
    el.addEventListener("wheel", onWheel, { passive: false })
    return () => el.removeEventListener("wheel", onWheel)
  }, [])

  const done = docs.filter((d) => !d.pending).length
  return (
    <div className="flex min-w-0 flex-1 items-center gap-1.5">
      <div
        ref={strip}
        className="flex min-w-0 flex-1 gap-1.5 overflow-x-auto px-2.5 py-1 [scrollbar-width:none] [mask-image:linear-gradient(90deg,transparent_0,#000_10px,#000_calc(100%-10px),transparent_100%)] [&::-webkit-scrollbar]:hidden"
      >
        {docs.map((d) => (
          <DocChip key={d.id} d={d} on={d.id === curId} onClick={() => onPick(d.id)} />
        ))}
      </div>
      {docs.length > 3 && (
        <Popover>
          <PopoverTrigger
            render={<Button variant="ghost" size="sm" className="shrink-0 rounded-full text-xs text-muted-foreground" />}
          >
            <ListIcon />
            <span className="tabular-nums">
              {done < docs.length ? `${done}/` : ""}
              {docs.length}
            </span>
          </PopoverTrigger>
          <PopoverContent align="end" className="max-h-[60vh] w-72 gap-0 overflow-y-auto p-1.5">
            <div className="px-2 pt-1.5 pb-1 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
              Dokumenty sprawy ({docs.length})
            </div>
            {docs.map((d) => (
              <button
                key={d.id}
                type="button"
                onClick={() => onPick(d.id)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted",
                  d.id === curId && "bg-accent hover:bg-accent",
                )}
              >
                <Dot d={d} />
                <span className="min-w-0 flex-1 truncate">{stem(d.file)}</span>
                <span className="shrink-0 text-[11px] text-muted-foreground">
                  {d.pending ? "…" : LABEL[d.doctype || ""] || d.doctype}
                </span>
              </button>
            ))}
          </PopoverContent>
        </Popover>
      )}
    </div>
  )
}

function Dot({ d }: { d: Doc }) {
  return d.pending ? (
    <Loader2 className="size-3 shrink-0 animate-spin text-primary" />
  ) : (
    <span className={cn("size-2 shrink-0 rounded-full", typeDot(d.doctype))} />
  )
}

function DocChip({ d, on, onClick }: { d: Doc; on: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      data-on={on}
      title={d.file}
      onClick={onClick}
      className={cn(
        "inline-flex h-8 max-w-[200px] shrink-0 items-center gap-2 rounded-full border px-3 text-[13px] whitespace-nowrap transition-colors",
        on ? "border-foreground bg-foreground text-background" : "bg-card text-secondary-foreground hover:bg-muted",
      )}
    >
      <Dot d={d} />
      <span className="truncate">{stem(d.file)}</span>
    </button>
  )
}
