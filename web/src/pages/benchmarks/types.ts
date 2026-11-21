// Shapes of docs/benchmarks.json (GET /api/benchmarks) and docs/bench_sweep.json (GET /api/bench_sweep).

export type Band = { max_b: number | null; points: number; label?: string }

export type BenchModel = {
  id: string
  name: string
  vendor?: string
  params_b: number | null
  active_b?: number | null
  arch?: "dense" | "moe" | "rules" | "router" | null
  f1: { train?: number | null; blind?: number | null; variants?: number | null }
  cost_usd?: { train?: number | null }
  chosen?: boolean
  placeholder?: boolean
  early?: boolean
  note?: string
}

export type OcrModel = {
  id: string
  name: string
  params_b?: number | null
  f1: number | null
  cost_usd?: number | null
  status?: string
  note?: string
  placeholder?: boolean
}

export type OcrLocal = { name: string; where: string; cer?: number | null; sec_per_page?: number | null; note?: string }

export type Profile8b = {
  profile: string
  avg_params_b?: number | null
  points?: number | null
  blind?: number | null
  variants?: number | null
  train?: number | null
  train_sample?: number | null
  uzp_scans?: number | null
  latency?: string
}

export type Benchmarks = {
  updated: string
  scoring: { title?: string; rule: string; bands: Band[] }
  datasets: { id: string; name: string; docs: number | null; desc: string }[]
  models: BenchModel[]
  ocr: { dataset: string; models: OcrModel[]; local: OcrLocal[] }
  real_corpus: { docs: number; agreement_low: number; agreement_high: number; desc: string }
  decision: { headline: string; points: string[] }
  profiles_8b?: Profile8b[]
}

export type SweepPart = {
  f1: number | null
  cost: number | null
  seconds: number | null
  per_doc: Record<string, number | null> | null
  negatives_ok?: string | null
  error?: string | null
}

/** One model of the sweep, after normalisation (see prepSweep). */
export type SweepRun = {
  model: string
  name?: string
  params_b: number | null
  points?: number | null
  eu_providers?: string[]
  providers?: string[]
  ts?: number
  train?: SweepPart | null
  blind?: SweepPart | null
  // derived
  label: string
  pts: number | null
  fb: number | null
  ft: number | null
  cost: number | null
  sec: number | null
  eu: boolean
  pareto: boolean
  special: string | null
}

export type SweepResponse = { runs?: unknown[]; mtime?: number | null; missing?: boolean }
