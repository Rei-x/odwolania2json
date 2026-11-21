import { useState } from "react"
import { Brain, Check, ChevronDown, Cpu, FlaskConical } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Slider } from "@/components/ui/slider"
import { MemoryChart } from "./memory-chart"
import { cn } from "@/lib/utils"
import {
  api,
  f3,
  levelModelLabel,
  type Model,
  pb,
  pname,
  type Profile,
  PROFILE_OPIS_FALLBACK,
  type Sample,
  type Stats,
} from "./lib"

/* ------------------------------------------------------------------ profile (cost / quality) */

/**
 * Quality/cost slider. Every piece has a fixed width and nothing next to it changes size when the level changes
 * (the legacy page re-flowed the header on "deterministyczny", which made the slider jump under the cursor).
 */
export function ProfileControl({
  profiles,
  profile,
  setProfile,
  models,
  override,
}: {
  profiles: Profile[]
  profile: string
  setProfile: (p: string) => void
  models: Model[]
  override: string | null
}) {
  const idx = Math.max(0, profiles.findIndex((p) => p.name === profile))
  return (
    <div className="flex h-9 shrink-0 items-center gap-2 rounded-full border bg-card pr-1 pl-3">
      <span className="hidden text-xs text-muted-foreground xl:inline">koszt</span>
      <div className="w-20 shrink-0 sm:w-24">
      <Slider
        aria-label="Profil: koszt / jakość"
        min={0}
        max={Math.max(1, profiles.length - 1)}
        step={1}
        value={[idx]}
        onValueChange={(v) => {
          const i = Array.isArray(v) ? v[0] : v
          const p = profiles[i]
          if (p && p.name !== profile) setProfile(p.name)
        }}
      />
      </div>
      <span className="hidden text-xs text-muted-foreground xl:inline">jakość</span>
      <Popover>
        <PopoverTrigger
          render={
            <button
              type="button"
              className="flex h-7 w-[9.5rem] shrink-0 flex-col items-start justify-center rounded-full px-2.5 text-left leading-none transition-colors hover:bg-muted"
            />
          }
        >
          <span className="w-full truncate text-xs font-semibold">{pname(profile)}</span>
          <span className="mt-0.5 w-full truncate font-mono text-[10px] text-muted-foreground">
            {levelModelLabel(profile, models, override)}
          </span>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-80 gap-1 p-1.5">
          <div className="px-2 pt-1.5 pb-1 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
            Profil przetwarzania
          </div>
          {profiles.map((p) => {
            const on = p.name === profile
            return (
              <button
                key={p.name}
                type="button"
                onClick={() => setProfile(p.name)}
                className={cn(
                  "grid w-full grid-cols-[14px_1fr] gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-muted",
                  on && "bg-accent hover:bg-accent",
                )}
              >
                <span className="pt-0.5 text-primary">{on && <Check className="size-3.5" />}</span>
                <span className="min-w-0">
                  <span className="flex items-baseline justify-between gap-2">
                    <b className="text-sm">{pname(p.name)}</b>
                    <span className="truncate font-mono text-[11px] text-muted-foreground">
                      {levelModelLabel(p.name, models, override)}
                    </span>
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {p.opis || PROFILE_OPIS_FALLBACK[p.name] || ""}
                  </span>
                </span>
              </button>
            )
          })}
          {override && (
            <p className="mx-2 my-1 rounded-md bg-muted px-2 py-1.5 text-xs text-muted-foreground">
              Wybrano model ręcznie, więc profile z LLM używają tylko jego.
            </p>
          )}
        </PopoverContent>
      </Popover>
    </div>
  )
}

/* ------------------------------------------------------------------ model picker */

function PointsBadge({ p }: { p: number | null }) {
  const cls =
    p == null
      ? "bg-muted text-muted-foreground"
      : p >= 18
        ? "bg-sage/15 text-sage"
        : p >= 8
          ? "bg-secondary text-secondary-foreground"
          : "bg-destructive/10 text-destructive"
  return (
    <span
      title={p == null ? "Rozmiar nieznany, brak punktów" : "Punkty UZP za rozmiar modelu"}
      className={cn("rounded-full px-1.5 py-px text-[10.5px] font-bold whitespace-nowrap", cls)}
    >
      {p ?? "?"} pkt
    </span>
  )
}

function EuBadge({ m }: { m: Model }) {
  return m.eu ? (
    <span
      title={`Serwowany przez dostawcę z UE: ${(m.eu_providers || []).join(", ")}`}
      className="rounded-full bg-primary/10 px-1.5 py-px text-[10.5px] font-bold text-primary"
    >
      UE
    </span>
  ) : (
    <span
      title="Brak dostawcy z siedzibą w UE/EOG: niezgodne z regulaminem, tylko do eksperymentów"
      className="rounded-full bg-wheat/25 px-1.5 py-px text-[10.5px] font-bold whitespace-nowrap text-bark"
    >
      poza UE
    </span>
  )
}

export function ModelPicker({
  models,
  model,
  setModel,
  profile,
  onOpen,
}: {
  models: Model[]
  model: string | null
  setModel: (m: string | null) => void
  profile: string
  onOpen: () => void
}) {
  const [open, setOpen] = useState(false)
  const det = profile === "deterministyczny"
  const m = models.find((x) => x.id === model)
  const choose = (id: string | null) => {
    setModel(id)
    setOpen(false)
    const mm = models.find((x) => x.id === id)
    toast(mm ? `Model: ${mm.name}${mm.eu ? "" : ", poza UE, tylko eksperyment"}` : "Model: automatyczny (wg profilu)")
  }
  const row = (x: Model) => (
    <button
      key={x.id}
      type="button"
      onClick={() => choose(x.id)}
      className={cn(
        "grid w-full grid-cols-[14px_minmax(0,1fr)_auto] items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-muted",
        x.id === model && "bg-accent hover:bg-accent",
      )}
    >
      <span className="text-primary">{x.id === model && <Check className="size-3.5" />}</span>
      <span className="min-w-0">
        <b className="block truncate text-[13px]">{x.name}</b>
        <small className="block truncate text-[11px] text-muted-foreground">
          {x.id}
          {x.f1_blind != null
            ? ` · F1 ślepy ${f3(x.f1_blind)}`
            : x.f1_train != null
              ? ` · F1 trening ${f3(x.f1_train)}`
              : ""}
          {x.cost != null ? ` · ${x.cost.toFixed(3).replace(".", ",")} $` : ""}
        </small>
      </span>
      <span className="flex items-center gap-1">
        <span className="rounded-full bg-muted px-1.5 py-px text-[10.5px] font-bold" title="Łączna liczba parametrów">
          {pb(x.params_b)}
        </span>
        <PointsBadge p={x.points} />
        <EuBadge m={x} />
      </span>
    </button>
  )
  const eu = models.filter((x) => x.eu)
  const non = models.filter((x) => !x.eu)
  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o)
        if (o) onOpen()
      }}
    >
      <PopoverTrigger
        disabled={det}
        title={
          det
            ? "Profil Reguły nie używa modelu LLM"
            : m
              ? `${m.name} (${m.id}) · ${pb(m.params_b)} · ${m.points ?? "?"} pkt${m.eu ? " · UE" : " · poza UE (tylko eksperyment)"}`
              : "Model: automatyczny (wg profilu)"
        }
        render={
          <Button
            variant="outline"
            className={cn(
              "h-9 w-[8.5rem] shrink-0 justify-start rounded-full px-3 sm:w-[10.5rem]",
              m && !det && "border-foreground/60",
              m && !m.eu && !det && "border-wheat",
            )}
          />
        }
      >
        <Cpu className="text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate text-left text-xs">{det ? "bez LLM" : m ? m.name : "Model: auto"}</span>
        <ChevronDown className="size-3 opacity-60" />
      </PopoverTrigger>
      <PopoverContent align="end" className="max-h-[min(70vh,560px)] w-[min(470px,calc(100vw-24px))] gap-0 overflow-y-auto p-1.5">
        <div className="flex justify-between px-2 pt-1.5 pb-1 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
          Model dla nowych dokumentów
          <span className="font-medium tracking-normal normal-case">OCR · klasyfikacja · ekstrakcja</span>
        </div>
        <button
          type="button"
          onClick={() => choose(null)}
          className={cn(
            "grid w-full grid-cols-[14px_1fr] items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-muted",
            !model && "bg-accent hover:bg-accent",
          )}
        >
          <span className="text-primary">{!model && <Check className="size-3.5" />}</span>
          <span>
            <b className="block text-[13px]">Automatyczny (wg profilu)</b>
            <small className="block text-[11px] text-muted-foreground">
              modele zdefiniowane w profilu {pname(profile)}
            </small>
          </span>
        </button>
        {eu.length > 0 && (
          <div className="px-2 pt-2.5 pb-1 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
            Hosting w UE
          </div>
        )}
        {eu.map(row)}
        {non.length > 0 && (
          <>
            <div className="px-2 pt-2.5 pb-1 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
              Poza UE (tylko eksperyment)
            </div>
            <p className="mx-2 mb-1 rounded-md bg-wheat/20 px-2 py-1.5 text-[11.5px] text-bark">
              Brak dostawcy z siedzibą w UE/EOG: wyniki tylko do porównań, niezgodne z regulaminem.
            </p>
            {non.map(row)}
          </>
        )}
        {!models.length && <p className="px-2 py-2 text-xs text-muted-foreground">Brak listy modeli (/api/models).</p>}
      </PopoverContent>
    </Popover>
  )
}

/* ------------------------------------------------------------------ learning memory */

export function MemoryButton({ stats }: { stats: Stats | null }) {
  const n = stats ? Object.values(stats.examples || {}).reduce((a, b) => a + b, 0) : null
  const tl = stats?.timeline || []
  return (
    <Popover>
      <PopoverTrigger
        title="Pamięć systemu: uczenie w czasie"
        render={<Button variant="outline" className="h-9 shrink-0 rounded-full px-3" />}
      >
        <Brain className="text-muted-foreground" />
        <span className="text-xs tabular-nums">
          {n == null ? "—" : n}
          <span className="hidden sm:inline"> dok.</span>
          {stats?.accuracy != null && (
            <span className="hidden text-muted-foreground lg:inline"> · {(stats.accuracy * 100).toFixed(1)}%</span>
          )}
        </span>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80">
        <div>
          <b className="text-sm">Uczenie w czasie</b>
          <p className="mt-0.5 text-xs text-muted-foreground">Zatwierdzone dokumenty uczą kolejne ekstrakcje.</p>
        </div>
        {tl.length > 0 && <MemoryChart timeline={tl} />}
        <div className="text-xs">
          Recenzji: <b>{stats?.reviews ?? 0}</b> · pól: {stats?.fields ?? 0} · poprawionych: {stats?.corrected ?? 0}
        </div>
        {(stats?.most_corrected || []).slice(0, 4).map(([f, c]) => (
          <div key={f} className="text-xs text-muted-foreground">
            • {f}: {c}×
          </div>
        ))}
      </PopoverContent>
    </Popover>
  )
}

/* ------------------------------------------------------------------ samples */

export function SamplesMenu({
  onPick,
  className,
  label = "Przykłady",
  alwaysLabel = false,
}: {
  onPick: (s: Sample) => void
  className?: string
  label?: string
  alwaysLabel?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [list, setList] = useState<Sample[] | null>(null)
  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o)
        if (o && !list) api.samples().then(setList).catch(() => setList([]))
      }}
    >
      <PopoverTrigger
        title="Przykładowe trudne dokumenty"
        render={<Button variant="ghost" size="sm" className={cn("rounded-full", className)} />}
      >
        <FlaskConical /> <span className={alwaysLabel ? "" : "hidden sm:inline"}>{label}</span>
      </PopoverTrigger>
      <PopoverContent align="end" className="max-h-[70vh] w-[min(360px,calc(100vw-24px))] gap-0 overflow-y-auto p-1.5">
        <div className="px-2 pt-1.5 pb-1 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
          Trudne przykłady
        </div>
        {list == null && <p className="px-2 py-2 text-xs text-muted-foreground">Ładowanie…</p>}
        {list?.length === 0 && <p className="px-2 py-2 text-xs text-muted-foreground">Brak przykładów.</p>}
        {list?.map((s) => (
          <button
            key={s.name}
            type="button"
            onClick={() => {
              setOpen(false)
              onPick(s)
            }}
            className="block w-full rounded-md px-2 py-2 text-left hover:bg-muted"
          >
            <b className="block text-[13px]">{s.title}</b>
            <small className="mt-0.5 block text-xs leading-snug text-muted-foreground">{s.opis}</small>
          </button>
        ))}
      </PopoverContent>
    </Popover>
  )
}

