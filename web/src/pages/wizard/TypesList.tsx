import { Lock } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import { typeColor, type DoctypeInfo } from "./types"
import { doctypeLabel } from "@/lib/labels"

/** Existing doctypes from config/doctypes/; click opens the YAML (built-ins read-only). */
export function TypesList({ types, onOpen, active }: { types: DoctypeInfo[] | null; onOpen: (name: string) => void; active?: string | null }) {
  if (!types)
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-12 rounded-lg" />
        ))}
      </div>
    )
  if (!types.length) return <p className="text-sm text-muted-foreground">Brak typów w config/doctypes/.</p>
  return (
    <ul className="-mx-1 space-y-0.5">
      {types.map((t) => (
        <li key={t.file}>
          <button
            type="button"
            onClick={() => onOpen(t.name)}
            className={cn(
              "flex w-full items-start gap-2.5 rounded-lg px-2 py-2 text-left transition-colors hover:bg-secondary",
              active === t.name && "bg-secondary",
            )}
          >
            <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", typeColor(t.name))} />
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-1.5 text-sm font-medium">
                <span className="truncate" title={`config/doctypes/${t.file}`}>{doctypeLabel(t.name)}</span>
                {t.builtin && <Lock aria-label="wbudowany (tylko do odczytu)" className="size-3 shrink-0 text-muted-foreground" />}
                {t.fields != null && <span className="ml-auto shrink-0 text-xs text-muted-foreground tabular-nums">{t.fields} pól</span>}
              </span>
              <span className={cn("line-clamp-1 text-xs text-muted-foreground", t.error && "text-destructive")}>
                {t.error ? "Błąd pliku: " + t.error : t.description}
              </span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}
