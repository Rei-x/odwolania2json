import type { InferResponse, DoctypeInfo, DoctypeMeta, DraftResponse, FieldRow, SaveResponse, TestResponse, Validation } from "./types"

export class ApiError extends Error {
  detail: unknown
  status: number
  constructor(msg: string, detail: unknown, status: number) {
    super(msg)
    this.detail = detail
    this.status = status
  }
  /** Line number reported by the backend (draft template errors), if any. */
  get line(): number | null {
    const d = this.detail as { line?: number } | null
    return d && typeof d === "object" && typeof d.line === "number" ? d.line : null
  }
}

async function api<T>(url: string, opt: RequestInit = {}): Promise<T> {
  const r = await fetch(url, opt)
  const t = await r.text()
  let j: unknown = null
  try {
    j = JSON.parse(t)
  } catch {
    /* plain text */
  }
  if (!r.ok) {
    const d = (j as { detail?: unknown } | null)?.detail
    const msg = typeof d === "string" ? d : (d as { msg?: string } | undefined)?.msg || t || r.statusText
    throw new ApiError(msg, d, r.status)
  }
  return j as T
}

const post = <T>(url: string, data: unknown, signal?: AbortSignal) =>
  api<T>(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data), signal })

export interface DraftPayload {
  name: string
  title: string
  description: string
  template?: string
  fields?: FieldRow[]
}

export const wizardApi = {
  list: () => api<DoctypeInfo[]>("/api/doctypes/list"),
  meta: () => api<DoctypeMeta>("/api/doctypes/meta"),
  yaml: (name: string) => api<{ name: string; yaml: string; builtin: boolean }>(`/api/doctypes/${encodeURIComponent(name)}/yaml`),
  draft: (p: DraftPayload, signal?: AbortSignal) => post<DraftResponse>("/api/doctypes/draft", p, signal),
  validate: (yaml: string, signal?: AbortSignal) => post<Validation>("/api/doctypes/validate", { yaml }, signal),
  test: (file: File, yaml: string) => {
    const fd = new FormData()
    fd.append("file", file)
    fd.append("yaml", yaml)
    return api<TestResponse>("/api/doctypes/test", { method: "POST", body: fd })
  },
  save: (yaml: string, overwrite: boolean, overwrite_builtin: boolean) =>
    post<SaveResponse>("/api/doctypes", { yaml, overwrite, overwrite_builtin }),
  remove: (name: string) => api<{ deleted: string }>(`/api/doctypes/${encodeURIComponent(name)}`, { method: "DELETE" }),
  /** Refresh the main app's doctype registry (legacy did the same after saving). */
  /** Example PDF(s) -> complete doctype draft proposed by the LLM (nothing is saved). */
  infer: (files: File[]) => {
    const fd = new FormData()
    for (const f of files) fd.append("files", f)
    return api<InferResponse>("/api/doctypes/infer", { method: "POST", body: fd })
  },
  touch: () => fetch("/api/doctypes").catch(() => {}),
}
