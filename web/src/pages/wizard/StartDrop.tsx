import { useRef, useState } from "react"
import { AlertCircle, Check, FileUp, Loader2, PencilLine } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { TypesList } from "./TypesList"
import type { Wizard } from "./useWizard"

const PHASES = [
  ["read", "Czytam dokument"],
  ["propose", "Proponuję pola"],
  ["test", "Testuję"],
] as const

/** Progress of the drop flow: read -> propose (one LLM call) -> test (extraction on the same PDF). */
export function InferProgress({ phase }: { phase: "read" | "propose" | "test" }) {
  const at = PHASES.findIndex(([k]) => k === phase)
  return (
    <ol className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-6" aria-live="polite">
      {PHASES.map(([k, label], i) => (
        <li key={k} className={cn("flex items-center gap-2 text-sm", i > at && "text-muted-foreground/60")}>
          <span
            className={cn(
              "grid size-6 place-items-center rounded-full border",
              i < at && "border-primary/40 bg-primary/10 text-primary",
              i === at && "border-primary text-primary",
            )}
          >
            {i < at ? <Check className="size-3.5" /> : i === at ? <Loader2 className="size-3.5 animate-spin" /> : null}
          </span>
          <span className={cn(i === at && "font-medium")}>{label}</span>
        </li>
      ))}
    </ol>
  )
}

export function StartDrop({ wiz }: { wiz: Wizard }) {
  const { s, set } = wiz
  const inp = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const busy = !!s.inferring
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <button
        type="button"
        disabled={busy}
        onClick={() => inp.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          if (!busy) setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          if (!busy) wiz.runInfer([...e.dataTransfer.files])
        }}
        className={cn(
          "group flex w-full flex-col items-center gap-4 rounded-3xl border-2 border-dashed bg-card px-6 py-16 text-center transition-colors sm:py-24",
          !busy && "hover:border-primary/50 hover:bg-accent/40",
          over && "border-primary bg-accent/60",
          busy && "cursor-progress border-primary/30",
        )}
      >
        <span className="grid size-16 place-items-center rounded-2xl bg-primary/10 text-primary transition-transform group-enabled:group-hover:-translate-y-0.5">
          {busy ? <Loader2 className="size-8 animate-spin" /> : <FileUp className="size-8" />}
        </span>
        {busy ? (
          <InferProgress phase={s.inferring!} />
        ) : (
          <>
            <span className="text-xl font-semibold tracking-tight">Upuść przykładowy dokument</span>
            <span className="text-sm text-muted-foreground">PDF, jeden lub kilka · resztę zaproponuje model</span>
          </>
        )}
      </button>
      <input
        ref={inp}
        type="file"
        accept=".pdf"
        multiple
        hidden
        data-testid="wz-infer-file"
        onChange={(e) => {
          const f = [...(e.target.files ?? [])]
          if (f.length) wiz.runInfer(f)
          e.target.value = ""
        }}
      />
      {s.inferErr && (
        <Alert variant="destructive">
          <AlertCircle />
          <AlertDescription>{s.inferErr}</AlertDescription>
        </Alert>
      )}
      <div className="flex justify-center">
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => set({ manual: true, inferErr: null })}>
          <PencilLine /> albo zdefiniuj ręcznie
        </Button>
      </div>
      <Card size="sm" className="gap-2">
        <CardHeader>
          <CardTitle className="text-sm">Istniejące typy</CardTitle>
        </CardHeader>
        <CardContent>
          <TypesList types={wiz.types} onOpen={wiz.openExisting} />
        </CardContent>
      </Card>
    </div>
  )
}
