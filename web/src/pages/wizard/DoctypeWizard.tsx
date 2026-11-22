import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { ArrowLeft, ArrowRight, FileUp, Loader2, Plus, Save, Wand2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { StepDefine } from "./StepDefine"
import { Stepper } from "./Stepper"
import { StepSave } from "./StepSave"
import { StepTest } from "./StepTest"
import { StepYaml } from "./StepYaml"
import { useWizard, type Wizard } from "./useWizard"
import { doctypeLabel } from "@/lib/labels"

function Footer({ wiz, force }: { wiz: Wizard; force: boolean }) {
  const { s } = wiz
  const navigate = useNavigate()
  const back = (label: string, k: 1 | 2 | 3) => (
    <Button variant="ghost" onClick={() => wiz.go(k)}>
      <ArrowLeft /> {label}
    </Button>
  )
  let left: React.ReactNode = null
  let msg: React.ReactNode = null
  let right: React.ReactNode = null
  if (s.step === 1 && !s.manual) {
    right = null
  } else if (s.step === 1) {
    right = (
      <Button onClick={wiz.generate} disabled={s.generating}>
        {s.generating ? <Loader2 className="animate-spin" /> : <Wand2 />} {s.generating ? "Generuję…" : "Generuj YAML"}
        {!s.generating && <ArrowRight />}
      </Button>
    )
  } else if (s.step === 2) {
    left = back("Definicja", 1)
    if (!s.readonly)
      right = (
        <>
          <Button variant="outline" onClick={() => wiz.requireValid(4)}>
            <Save /> Zapisz
          </Button>
          <Button onClick={() => wiz.requireValid(3)}>
            Testuj <ArrowRight />
          </Button>
        </>
      )
  } else if (s.step === 3) {
    left = back("YAML", 2)
    right = (
      <>
        {s.test && !s.testing && (
          <Button variant="outline" onClick={wiz.clearTest}>
            <FileUp /> Inny PDF
          </Button>
        )}
        {!s.readonly && (
          <Button onClick={wiz.quickSave} disabled={s.testing} className="bg-success text-white hover:bg-success/85">
            <Save /> Zapisz
          </Button>
        )}
      </>
    )
  } else if (s.saved) {
    left = (
      <Button variant="ghost" onClick={wiz.reset}>
        <Plus /> Kolejny typ
      </Button>
    )
    right = (
      <>
        {s.testFile && (
          <Button
            variant="outline"
            title="Pełny potok: klasyfikacja (reguły + LLM) → ekstrakcja → weryfikacja"
            onClick={() => navigate("/app", { state: { files: [s.testFile] } })}
          >
            <span className="max-w-48 truncate">Przetwórz {s.testFile.name}</span>
          </Button>
        )}
        <Button
          onClick={() => {
            toast(`Typ „${doctypeLabel(s.saved!.name)}” gotowy — wgraj PDF`)
            navigate("/app")
          }}
        >
          Do aplikacji <ArrowRight />
        </Button>
      </>
    )
  } else {
    left = back(s.test ? "Test" : "YAML", s.test ? 3 : 2)
    msg = s.saveErr && <span className="text-destructive">{s.saveErr}</span>
    right = (
      <Button onClick={() => wiz.save(force)} disabled={!s.valid?.ok || s.saving} className="bg-success text-white hover:bg-success/85">
        {s.saving ? <Loader2 className="animate-spin" /> : <Save />} {s.saving ? "Zapisuję…" : "Zapisz"}
      </Button>
    )
  }
  if (!left && !msg && !right) return null
  return (
    <div className="sticky bottom-0 z-30 border-t bg-background/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-2 px-4 py-3">
        {left}
        {msg && <span className="min-w-0 flex-1 text-xs text-muted-foreground max-sm:order-first max-sm:basis-full">{msg}</span>}
        <div className="ml-auto flex flex-wrap justify-end gap-2">{right}</div>
      </div>
    </div>
  )
}

/** The whole "Nowy typ dokumentu" wizard; self-contained so it can also live in a dialog. */
export function DoctypeWizard({ className }: { className?: string }) {
  const wiz = useWizard()
  const [force, setForce] = useState(false)
  const { s } = wiz
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [s.step])
  useEffect(() => setForce(false), [s.name])
  return (
    <div className={cn("flex min-h-0 flex-1 flex-col", className)}>
      <div className="mx-auto w-full max-w-[1400px] flex-1 px-4 pt-6 pb-8">
        <div className="mb-5 flex flex-wrap items-center gap-x-6 gap-y-3">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight">Nowy typ dokumentu</h1>
            <p className="text-sm text-muted-foreground">Jeden plik YAML, zero zmian w kodzie.</p>
          </div>
          <div className="ml-auto">
            <Stepper step={s.step} canGo={wiz.canGo} onGo={wiz.go} />
          </div>
        </div>
        {s.step === 1 && <StepDefine wiz={wiz} />}
        {s.step === 2 && <StepYaml wiz={wiz} />}
        {s.step === 3 && <StepTest wiz={wiz} />}
        {s.step === 4 && <StepSave wiz={wiz} force={force} setForce={setForce} />}
      </div>
      <Footer wiz={wiz} force={force} />
    </div>
  )
}
