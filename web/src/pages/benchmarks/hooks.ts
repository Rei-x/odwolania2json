import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { prepSweep } from "./lib"
import type { Benchmarks, SweepResponse, SweepRun } from "./types"

export function useBenchmarks() {
  const [data, setData] = useState<Benchmarks | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const ctl = new AbortController()
    fetch("/api/benchmarks", { signal: ctl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: Benchmarks) => setData(d))
      .catch((e: Error) => e.name !== "AbortError" && setError(e.message))
    return () => ctl.abort()
  }, [])
  return { data, error }
}

const hm = (d: Date, s = false) =>
  d.toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit", ...(s ? { second: "2-digit" } : {}) })

/** Model sweep results; re-polled every 30 s while `auto` is on (the sweep appends results while it runs). */
export function useSweep() {
  const [raw, setRaw] = useState<unknown[] | null>(null)
  const [mtime, setMtime] = useState<number | null>(null)
  const [status, setStatus] = useState("")
  const [loading, setLoading] = useState(false)
  const [auto, setAuto] = useState(true)
  const [seen, setSeen] = useState<Set<string> | null>(null)
  const lastMtime = useRef<number | null | undefined>(undefined)
  const lastModels = useRef<Set<string> | null>(null)

  const load = useCallback((force: boolean) => {
    setLoading(true)
    return fetch("/api/bench_sweep", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: SweepResponse) => {
        const runs = Array.isArray(d.runs) ? d.runs : []
        const t = d.mtime ? new Date(d.mtime * 1000) : null
        setStatus(`${runs.length} modeli${t ? " · plik z " + hm(t) : ""} · sprawdzono ${hm(new Date(), true)}`)
        if (!force && d.mtime === lastMtime.current && lastModels.current) return
        lastMtime.current = d.mtime ?? null
        setSeen(lastModels.current) // models known before this refresh; the rest get highlighted
        lastModels.current = new Set(runs.map((r) => String((r as { model?: unknown }).model)))
        setMtime(d.mtime ?? null)
        setRaw(runs)
      })
      .catch((e: Error) => setStatus("Błąd odświeżania: " + e.message))
      .finally(() => setTimeout(() => setLoading(false), 300))
  }, [])

  useEffect(() => {
    load(true)
  }, [load])
  useEffect(() => {
    if (!auto) return
    const id = setInterval(() => !document.hidden && load(false), 30000)
    return () => clearInterval(id)
  }, [auto, load])

  const runs: SweepRun[] | null = useMemo(() => (raw ? prepSweep(raw) : null), [raw])

  return { runs, mtime, status, loading, auto, setAuto, refresh: () => load(true), seen }
}
