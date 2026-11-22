import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { rememberDoctypes } from "@/lib/labels"
import { ApiError, wizardApi } from "./api"
import {
  DEFAULT_BUILTIN,
  NAME_RE,
  SAMPLE_DESC,
  SAMPLE_NAME,
  SAMPLE_TITLE,
  SAMPLE_TPL,
  newRow,
  type DoctypeInfo,
  type DoctypeMeta,
  type FieldRow,
  type SaveResponse,
  type TestResponse,
  type Validation,
} from "./types"

export type Step = 1 | 2 | 3 | 4
export type Mode = "template" | "table"
export type InferPhase = "read" | "propose" | null

export interface WizardState {
  step: Step
  maxStep: Step
  mode: Mode
  name: string
  title: string
  desc: string
  template: string
  rows: FieldRow[]
  yaml: string
  /** Built-in type opened for viewing: editor is read-only. */
  readonly: boolean
  /** Name of an existing custom type being edited (save overwrites it). */
  editing: string | null
  draftErr: string | null
  generating: boolean
  valid: Validation | null
  validating: boolean
  test: TestResponse | null
  testing: boolean
  testFile: File | null
  saved: SaveResponse | null
  saving: boolean
  saveErr: string | null
  /** Drop-a-document flow: progress, warnings and cost of the LLM proposal; `manual` shows the template/table form. */
  inferring: InferPhase
  inferErr: string | null
  inferWarnings: string[]
  inferCost: number | null
  manual: boolean
}

const INITIAL: WizardState = {
  step: 1,
  maxStep: 1,
  mode: "template",
  name: "",
  title: "",
  desc: "",
  template: "",
  rows: [newRow()],
  yaml: "",
  readonly: false,
  editing: null,
  draftErr: null,
  generating: false,
  valid: null,
  validating: false,
  test: null,
  testing: false,
  testFile: null,
  saved: null,
  saving: false,
  saveErr: null,
  inferring: null,
  inferErr: null,
  inferWarnings: [],
  inferCost: null,
  manual: false,
}

/** Path into the nested field table: indices of rows, descending through `children`. */
export type RowPath = number[]

function mapAt(rows: FieldRow[], path: RowPath, fn: (arr: FieldRow[], idx: number) => FieldRow[]): FieldRow[] {
  const [i, ...rest] = path
  if (!rest.length) return fn(rows, i)
  return rows.map((r, k) => (k === i ? { ...r, children: mapAt(r.children ?? [], rest, fn) } : r))
}

export function useWizard() {
  const [s, setS] = useState<WizardState>(INITIAL)
  const [types, setTypes] = useState<DoctypeInfo[] | null>(null)
  const [meta, setMeta] = useState<DoctypeMeta | null>(null)
  const set = useCallback((patch: Partial<WizardState> | ((s: WizardState) => Partial<WizardState>)) => {
    setS((prev) => {
      const p = typeof patch === "function" ? patch(prev) : patch
      const next = { ...prev, ...p }
      if (next.step > next.maxStep) next.maxStep = next.step
      return next
    })
  }, [])

  const loadTypes = useCallback(
    () =>
      wizardApi
        .list()
        .then((t) => {
          rememberDoctypes(t)
          setTypes(t)
        })
        .catch(() => setTypes((t) => t ?? [])),
    [],
  )

  useEffect(() => {
    loadTypes()
    wizardApi.meta().then(setMeta).catch(() => {})
  }, [loadTypes])

  // ---------- live validation of the YAML (debounced, latest request wins)
  const vSeq = useRef(0)
  useEffect(() => {
    if (!s.yaml) return
    const seq = ++vSeq.current
    const ctl = new AbortController()
    setS((p) => ({ ...p, validating: true }))
    const t = setTimeout(() => {
      wizardApi
        .validate(s.yaml, ctl.signal)
        .then((v) => {
          if (seq !== vSeq.current) return
          setS((p) => ({ ...p, valid: v, validating: false, name: v.name || p.name }))
        })
        .catch((e: unknown) => {
          if (seq !== vSeq.current || (e as Error).name === "AbortError") return
          setS((p) => ({ ...p, validating: false, valid: { ok: false, errors: [{ line: null, path: "", msg: (e as Error).message }], warnings: [] } }))
        })
    }, 350)
    return () => {
      clearTimeout(t)
      ctl.abort()
    }
  }, [s.yaml])

  const builtinNames = meta?.builtin ?? DEFAULT_BUILTIN
  const typeList = types ?? []

  // ---------- navigation
  const canGo = (k: Step) =>
    k <= s.maxStep || (!!s.yaml && (k === 2 || k === 3)) || (k === 4 && !!s.yaml && !s.readonly)
  const go = (k: Step) => {
    if (canGo(k)) set({ step: k })
  }

  // ---------- step 1
  const nameIssue = s.name && !NAME_RE.test(s.name) ? "Nazwa: małe litery, cyfry i _, zaczyna się literą." : null
  const nameExists = !!s.name && typeList.some((t) => t.name === s.name)

  const insertSample = () =>
    set((p) => ({
      template: SAMPLE_TPL,
      name: p.name || SAMPLE_NAME,
      title: p.title || SAMPLE_TITLE,
      desc: p.desc || SAMPLE_DESC,
      draftErr: null,
    }))

  const rows = {
    update: (path: RowPath, patch: Partial<FieldRow>) =>
      set((p) => ({
        rows: mapAt(p.rows, path, (arr, i) =>
          arr.map((r, k) => {
            if (k !== i) return r
            const n = { ...r, ...patch }
            if ((n.type === "object" || n.type === "array") && !(n.children ?? []).length) n.children = [newRow()]
            return n
          }),
        ),
      })),
    remove: (path: RowPath) => set((p) => ({ rows: mapAt(p.rows, path, (arr, i) => arr.filter((_, k) => k !== i)) })),
    addChild: (path: RowPath) =>
      set((p) => ({
        rows: mapAt(p.rows, path, (arr, i) => arr.map((r, k) => (k === i ? { ...r, children: [...(r.children ?? []), newRow()] } : r))),
      })),
    add: (kind: "field" | "object" | "array") =>
      set((p) => ({
        rows: [
          ...p.rows,
          kind === "field" ? newRow() : { name: "", type: kind, description: "", children: [newRow()] },
        ],
      })),
  }

  const generate = async () => {
    if (!NAME_RE.test(s.name)) return set({ draftErr: "Podaj nazwę techniczną: małe litery, cyfry i _, np. faktura." })
    const payload: Parameters<typeof wizardApi.draft>[0] = { name: s.name, title: s.title, description: s.desc }
    if (s.mode === "template") {
      if (!s.template.trim()) return set({ draftErr: "Wklej szablon JSON albo przełącz na tabelę pól." })
      payload.template = s.template
    } else payload.fields = s.rows
    set({ draftErr: null, generating: true })
    try {
      const r = await wizardApi.draft(payload)
      set({
        yaml: r.yaml,
        valid: r.validation,
        readonly: false,
        test: null,
        saved: null,
        step: 2,
        maxStep: 3,
        generating: false,
        editing: typeList.some((t) => t.name === s.name && !t.builtin) ? s.name : null,
      })
    } catch (e) {
      const err = e as ApiError
      set({ generating: false, draftErr: err.line ? `${err.message} (linia ${err.line})` : err.message })
    }
  }

  const openExisting = async (name: string) => {
    try {
      const r = await wizardApi.yaml(name)
      set({
        yaml: r.yaml,
        valid: null,
        readonly: r.builtin,
        editing: r.builtin ? null : name,
        name,
        test: null,
        testFile: null,
        saved: null,
        step: 2,
        maxStep: r.builtin ? 2 : 4,
      })
    } catch (e) {
      toast.error("Nie udało się wczytać: " + (e as Error).message)
    }
  }

  // ---------- step 2
  const setYaml = (yaml: string) => set({ yaml, test: null })

  const duplicate = () => {
    const nn = s.name + "_kopia"
    set((p) => ({
      yaml: p.yaml.replace(/^name:\s*.*$/m, `name: ${nn}`),
      name: nn,
      readonly: false,
      editing: null,
      maxStep: 3,
    }))
    toast(`Skopiowano jako „${nn}” — zmień nazwę i pola`)
  }

  const deleteEditing = async () => {
    const name = s.editing
    if (!name) return
    try {
      await wizardApi.remove(name)
      toast.success(`Usunięto typ „${name}”`)
      set({ editing: null, yaml: "", valid: null, step: 1, maxStep: 1, test: null, saved: null })
      loadTypes()
    } catch (e) {
      toast.error("Błąd: " + (e as Error).message)
    }
  }

  const requireValid = (step: Step) => {
    if (s.valid?.ok) set({ step, ...(step === 4 ? { maxStep: 4 as Step } : {}) })
    else toast.error("Najpierw popraw błędy w YAML")
  }

  // ---------- step 3
  const runTest = async (file: File, yaml: string = s.yaml, jump = false) => {
    set({ testing: true, testFile: file, test: null })
    try {
      const r = await wizardApi.test(file, yaml)
      // auto-test after inference: show the result as soon as it is there (unless the user went elsewhere)
      set((p) => ({ test: r, testing: false, ...(jump && p.step === 2 ? { step: 3 as Step } : {}) }))
    } catch (e) {
      set({ test: null, testing: false })
      toast.error("Test nieudany: " + (e as Error).message)
    }
  }
  const clearTest = () => set({ test: null })

  // ---------- drop a document: LLM proposes the whole type, then it is tested on the same PDF
  const runInfer = async (files: File[]) => {
    const pdfs = files.filter((f) => /\.pdf$/i.test(f.name)).slice(0, 5)
    if (!pdfs.length) return set({ inferErr: "Wgraj plik PDF." })
    set({ inferring: "read", inferErr: null, inferWarnings: [], inferCost: null })
    const t = setTimeout(() => set((p) => (p.inferring ? { inferring: "propose" } : {})), 2500)
    try {
      const r = await wizardApi.infer(pdfs)
      clearTimeout(t)
      set({
        inferring: null,
        yaml: r.yaml,
        valid: r.validation,
        name: (rememberDoctypes([r.spec]), r.spec.name),
        readonly: false,
        editing: null,
        saved: null,
        test: null,
        inferWarnings: r.warnings,
        inferCost: r.cost,
        step: 2,
        maxStep: 3,
      })
      if (r.validation.ok) runTest(pdfs[0], r.yaml, true)
    } catch (e) {
      clearTimeout(t)
      set({ inferring: null, inferErr: (e as Error).message })
    }
  }

  /** One-click save from the test step (built-in names still go through the confirmation in step 4). */
  const quickSave = async () => {
    if (!s.valid?.ok) return toast.error("Najpierw popraw błędy w YAML")
    set({ step: 4, maxStep: 4 })
    if (!isBuiltin) await save(false)
  }

  // ---------- step 4
  const isBuiltin = builtinNames.includes(s.name)
  const save = async (force: boolean) => {
    if (isBuiltin && !force) return set({ saveErr: "Zaznacz zgodę na nadpisanie typu wbudowanego." })
    set({ saving: true, saveErr: null })
    try {
      const r = await wizardApi.save(s.yaml, nameExists, isBuiltin && force)
      set({ saved: r, editing: r.name, saving: false })
      loadTypes()
      wizardApi.touch()
    } catch (e) {
      set({ saving: false, saveErr: (e as Error).message })
    }
  }

  const reset = () => setS({ ...INITIAL, rows: [newRow()] })

  return {
    s,
    set,
    types,
    meta,
    builtinNames,
    canGo,
    go,
    nameIssue,
    nameExists,
    isBuiltin,
    insertSample,
    rows,
    generate,
    openExisting,
    setYaml,
    duplicate,
    deleteEditing,
    requireValid,
    runTest,
    clearTest,
    runInfer,
    quickSave,
    save,
    reset,
    loadTypes,
  }
}

export type Wizard = ReturnType<typeof useWizard>
