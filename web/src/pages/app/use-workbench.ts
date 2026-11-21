import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { api, type Doc, type Json, type JsonObj, type Model, type Profile, type Stats, setP } from "./lib"

const LS_MODEL = "o2j.model"
const LS_PROFILE = "o2j.profile"
const lsGet = (k: string) => {
  try {
    return localStorage.getItem(k)
  } catch {
    return null
  }
}
const lsSet = (k: string, v: string | null) => {
  try {
    if (v) localStorage.setItem(k, v)
    else localStorage.removeItem(k)
  } catch {
    /* storage unavailable */
  }
}

const FALLBACK_PROFILES: Profile[] = ["deterministyczny", "ekonomiczny", "standard", "maksymalny"].map((name) => ({
  name,
  opis: "",
}))

export function useWorkbench() {
  const [docs, setDocs] = useState<Doc[]>([])
  const [curId, setCurId] = useState<number | null>(null)
  const [profiles, setProfiles] = useState<Profile[]>(FALLBACK_PROFILES)
  const [profile, setProfileState] = useState<string>("standard")
  const [models, setModels] = useState<Model[]>([])
  const [model, setModelState] = useState<string | null>(() => lsGet(LS_MODEL))
  const [stats, setStats] = useState<Stats | null>(null)
  const caseId = useRef<string | null>(null)
  const nextId = useRef(1)

  useEffect(() => {
    api
      .profiles()
      .then((p) => {
        setProfiles(p.profiles)
        const saved = lsGet(LS_PROFILE)
        const names = p.profiles.map((x) => x.name)
        setProfileState(saved && names.includes(saved) ? saved : p.default && names.includes(p.default) ? p.default : names[0])
      })
      .catch(() => {})
  }, [])

  const loadModels = useCallback(
    () =>
      api
        .models()
        .then((d) => {
          const list = d.models || []
          setModels(list)
          setModelState((m) => (m && !list.some((x) => x.id === m) ? null : m))
        })
        .catch(() => {}),
    [],
  )
  const loadStats = useCallback(() => api.stats().then(setStats).catch(() => {}), [])
  useEffect(() => {
    loadModels()
    loadStats()
  }, [loadModels, loadStats])

  const setProfile = useCallback((p: string) => {
    setProfileState(p)
    lsSet(LS_PROFILE, p)
  }, [])
  const setModel = useCallback((m: string | null) => {
    setModelState(m)
    lsSet(LS_MODEL, m)
  }, [])

  const patch = useCallback((id: number, p: Partial<Doc>) => {
    setDocs((ds) => ds.map((d) => (d.id === id ? { ...d, ...p } : d)))
  }, [])

  // keep the latest profile/model for async upload callbacks
  const opts = useRef({ profile, model })
  opts.current = { profile, model }

  const add = useCallback(
    (files: File[]) => {
      if (!files.length) return
      if (!caseId.current) caseId.current = Math.random().toString(36).slice(2, 12)
      const cid = caseId.current
      const { profile: prof, model: mdl } = opts.current
      const fresh: Doc[] = files.map((f) => ({ id: nextId.current++, file: f.name, pending: true }))
      setDocs((ds) => [...ds, ...fresh])
      setCurId(fresh[0].id)
      let left = files.length
      files.forEach((f, i) => {
        const id = fresh[i].id
        api
          .process(f, cid, prof, mdl)
          .then((d) => patch(id, { ...d.documents[0], pending: false }))
          .catch((err: Error) =>
            patch(id, { pending: false, doctype: "error", error: err.message, result: {}, trace: {} }),
          )
          .finally(() => {
            if (--left === 0) toast.success(`Gotowe · ${files.length} ${files.length === 1 ? "dokument" : "dokumenty"}`)
          })
      })
    },
    [patch],
  )

  const editField = useCallback((id: number, path: string, val: Json) => {
    setDocs((ds) =>
      ds.map((d) => {
        if (d.id !== id) return d
        const edited: JsonObj = structuredClone(d.edited || d.result || {})
        setP(edited, path, val)
        return { ...d, edited }
      }),
    )
  }, [])

  // one feedback request per document at a time (double clicks must not store the same review twice)
  const saving = useRef(new Set<number>())
  const [savingIds, setSavingIds] = useState<number[]>([])
  const approve = useCallback(
    (d: Doc) => {
      if (!d.session || saving.current.has(d.id)) return
      saving.current.add(d.id)
      setSavingIds([...saving.current])
      api
        .feedback(d.session, d.file, d.edited || d.result || {})
        .then((res) => {
          patch(d.id, { approved: true, ...(d.edited ? { result: d.edited, edited: null } : {}) })
          loadStats()
          toast.success(
            res.corrected_fields
              ? `Zapisano ${res.corrected_fields} poprawek w pamięci`
              : "Zatwierdzono, dokument dodany do pamięci",
          )
        })
        .catch((e: Error) => toast.error("Błąd zapisu: " + e.message))
        .finally(() => {
          saving.current.delete(d.id)
          setSavingIds([...saving.current])
        })
    },
    [patch, loadStats],
  )

  const cur = docs.find((d) => d.id === curId) ?? null
  return {
    docs,
    cur,
    setCurId,
    profiles,
    profile,
    setProfile,
    models,
    loadModels,
    model,
    setModel,
    stats,
    caseId: caseId.current,
    add,
    editField,
    approve,
    savingIds,
  }
}

export type Workbench = ReturnType<typeof useWorkbench>
