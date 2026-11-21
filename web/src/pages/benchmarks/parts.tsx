import type { ReactNode } from "react"
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { bandStrength } from "./lib"

export function Section({ id, title, lead, aside, children }: { id: string; title: ReactNode; lead?: ReactNode; aside?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-32 pt-14 sm:pt-16">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-3xl">
          <h2 className="text-2xl font-semibold tracking-tight text-balance sm:text-3xl">{title}</h2>
          {lead && <p className="mt-2 text-[15px] leading-relaxed text-pretty text-muted-foreground">{lead}</p>}
        </div>
        {aside}
      </div>
      {children}
    </section>
  )
}

export const Dash = ({ children = "—" }: { children?: ReactNode }) => <span className="text-muted-foreground/60">{children}</span>

export const Pending = () => <span className="text-xs whitespace-nowrap text-primary italic">w trakcie pomiaru</span>

/** "brak wyniku" with the run's error on hover. */
export function NoResult({ error, children = "brak wyniku" }: { error?: string | null; children?: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={<span />}
        className="cursor-help border-b border-dotted border-chart-3/70 text-xs whitespace-nowrap text-chart-3 italic"
      >
        {children}
      </TooltipTrigger>
      <TooltipContent className="max-w-sm break-words">{error || "Brak wyniku (pomiar w toku albo przebieg nie zwrócił danych)"}</TooltipContent>
    </Tooltip>
  )
}

/** UZP size points as a pill tinted by band. */
export function PointsPill({ p }: { p: number | null | undefined }) {
  if (p == null) return <Dash />
  return (
    <span
      className={cn(
        "inline-block min-w-12 rounded-full px-2 py-0.5 text-center text-xs font-semibold tabular-nums",
        p >= 12 ? "text-success" : "text-muted-foreground",
      )}
      style={{ background: `color-mix(in oklab, var(--sage) ${Math.round(Math.max(0.08, bandStrength(p) + 0.04) * 100)}%, transparent)` }}
    >
      {p} pkt
    </span>
  )
}

/** Small badge with a hover explanation. */
export function HintBadge({ hint, className, children }: { hint: ReactNode; className?: string; children: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={<span />}
        className={cn("inline-flex h-5 cursor-help items-center rounded-full px-1.5 text-[10.5px] font-semibold whitespace-nowrap", className)}
      >
        {children}
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">{hint}</TooltipContent>
    </Tooltip>
  )
}

export const EuBadge = ({ eu, providers }: { eu: string[]; providers?: string[] }) =>
  eu.length ? (
    <HintBadge hint={`Dostawcy z UE: ${eu.join(", ")}`} className="bg-chart-2/15 text-sage">
      UE
    </HintBadge>
  ) : (
    <HintBadge
      hint={`Brak dostawcy z siedzibą w UE/EOG${providers?.length ? ": " + providers.join(", ") : ""}`}
      className="bg-wheat/25 text-chart-3"
    >
      poza UE
    </HintBadge>
  )

/** Sortable table header button. */
export function SortHead({
  label,
  active,
  dir,
  onClick,
  align = "left",
  title,
}: {
  label: ReactNode
  active: boolean
  dir: 1 | -1
  onClick: () => void
  align?: "left" | "right"
  title?: string
}) {
  const Icon = !active ? ArrowUpDown : dir > 0 ? ArrowUp : ArrowDown
  return (
    <button
      type="button"
      onClick={onClick}
      title={title ?? "Sortuj"}
      className={cn(
        "inline-flex items-center gap-1 text-[10.5px] font-semibold tracking-normal whitespace-nowrap uppercase transition-colors hover:text-foreground",
        active ? "text-foreground" : "text-muted-foreground",
        align === "right" && "flex-row-reverse",
      )}
    >
      {label}
      <Icon className={cn("size-3", !active && "opacity-40")} />
    </button>
  )
}

export function useSort<K extends string>(key: K, setKey: (k: K) => void, dir: 1 | -1, setDir: (d: 1 | -1) => void, defaultDir: (k: K) => 1 | -1 = () => 1) {
  return (k: K) => {
    if (k === key) setDir(dir > 0 ? -1 : 1)
    else {
      setKey(k)
      setDir(defaultDir(k))
    }
  }
}

export const cmp = (x: number | string, y: number | string) => (x > y ? 1 : x < y ? -1 : 0)
