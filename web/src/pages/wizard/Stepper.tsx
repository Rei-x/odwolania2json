import { Check } from "lucide-react"
import { cn } from "@/lib/utils"
import { STEPS } from "./types"
import type { Step } from "./useWizard"

export function Stepper({ step, canGo, onGo }: { step: Step; canGo: (k: Step) => boolean; onGo: (k: Step) => void }) {
  return (
    <ol className="flex items-center gap-1 sm:gap-2" aria-label="Kroki kreatora">
      {STEPS.map((label, i) => {
        const k = (i + 1) as Step
        const on = k === step
        const done = k < step
        const enabled = canGo(k)
        return (
          <li key={label} className="flex items-center gap-1 sm:gap-2">
            {i > 0 && <span className={cn("h-px w-3 bg-border sm:w-6", done || on ? "bg-primary/50" : "")} aria-hidden />}
            <button
              type="button"
              disabled={!enabled}
              aria-current={on ? "step" : undefined}
              onClick={() => onGo(k)}
              className={cn(
                "group flex items-center gap-2 rounded-full py-1 pr-1 pl-1 text-sm transition-colors sm:pr-3",
                "disabled:cursor-not-allowed disabled:opacity-45",
                on ? "bg-secondary text-foreground" : "text-muted-foreground enabled:hover:text-foreground",
              )}
            >
              <span
                className={cn(
                  "grid size-6 place-items-center rounded-full border text-xs font-semibold tabular-nums",
                  on && "border-primary bg-primary text-primary-foreground",
                  done && "border-primary/40 bg-primary/10 text-primary",
                  !on && !done && "border-border bg-card",
                )}
              >
                {done ? <Check className="size-3.5" /> : k}
              </span>
              <span className={cn("hidden sm:inline", on && "font-medium")}>{label}</span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}
