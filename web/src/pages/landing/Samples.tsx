import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { Badge } from "@/components/ui/badge"
import { ArrowIcon, SectionHead } from "./Reveal"

type Sample = { name: string; title: string; opis: string; kind?: string; typ?: string; files?: string[] }

const KIND: Record<string, string> = { skan: "skan", wariant: "trudny wariant", sprawa: "cała sprawa", negatyw: "poza zakresem", czysty: "czysty PDF" }

/** "Trudne dokumenty": samples from /api/samples, each opening in the workbench. */
export function Samples() {
  const [list, setList] = useState<Sample[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const ac = new AbortController()
    fetch("/api/samples", { signal: ac.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Sample[]) => setList(d))
      .catch((e: unknown) => { if (!ac.signal.aborted) { console.warn("samples:", e); setFailed(true) } })
    return () => ac.abort()
  }, [])

  return (
    <section className="sec" id="wyprobuj">
      <div className="wrap">
        <SectionHead eyebrow="Wypróbuj" title="Sprawdź na trudnych dokumentach.">
          <p className="lede">Skany, szum, pieczęcie i zdjęcia z telefonu. Kliknij, by otworzyć w aplikacji.</p>
        </SectionHead>
        {failed ? (
          <p style={{ color: "var(--mute)" }}>Przykłady są dostępne w aplikacji.</p>
        ) : (
          <div className="samples" aria-busy={!list}>
            {!list
              ? Array.from({ length: 5 }, (_, i) => <div className="sm sk" key={i} />)
              : list.map((s) => (
                  <Link className="sm" key={s.name} to={`/app?sample=${encodeURIComponent(s.name)}`}>
                    <div className="th">
                      <Badge className={`k ${s.kind ?? ""}`}>{KIND[s.kind ?? ""] ?? s.kind ?? ""}</Badge>
                      <img loading="lazy" decoding="async" alt="" width={400} height={360} src={`/samples/${encodeURIComponent(s.name.replace(/\.pdf$/i, ""))}.webp`} />
                      <span className="go"><ArrowIcon /></span>
                    </div>
                    <div className="bd"><b>{s.title}</b><p>{s.opis}</p></div>
                  </Link>
                ))}
          </div>
        )}
      </div>
    </section>
  )
}
