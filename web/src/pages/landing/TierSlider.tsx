import { useState, type CSSProperties, type ReactNode } from "react"
import { cn } from "@/lib/utils"
import { Reveal, SectionHead } from "./Reveal"

type Comp = "rules" | "llm" | "verify" | "router" | "vote"
type Tier = { n: string; d: string; f: string[]; c: Comp[]; g: string; x: string }

const mix = (token: string, pct: number) => `color-mix(in oklab, ${token} ${pct}%, transparent)`

const TIERS: Tier[] = [
  { n: "Reguły", d: "Bez LLM. Deterministycznie.", f: ["0 zł", "180 dok. w 2,9 s"], c: ["rules"], g: mix("var(--teal-l)", 32), x: "10%" },
  { n: "Ekonomiczny", d: "Lekki model, bez pętli naprawy.", f: ["najtańszy z LLM"], c: ["llm"], g: mix("var(--teal-l)", 26), x: "30%" },
  { n: "Standard", d: "Szybki model z weryfikacją.", f: ["domyślny"], c: ["llm", "verify"], g: mix("var(--wheat)", 26), x: "50%" },
  { n: "Auto", d: "Tanio dla łatwych, mocny model dla trudnych.", f: ["eskalacja tylko dla trudnych"], c: ["rules", "llm", "verify", "router"], g: mix("var(--wheat)", 30), x: "70%" },
  { n: "Maksymalny", d: "Kilka modeli głosuje nad każdym polem.", f: ["najwyższa jakość"], c: ["llm", "verify", "vote"], g: mix("var(--acc)", 34), x: "90%" },
]

const svg = (d: ReactNode) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
)

const COMPS: { id: Comp; color: string; icon: ReactNode; title: string }[] = [
  { id: "rules", color: "var(--teal-l)", icon: svg(<path d="M4 6h16M4 12h10M4 18h7" />), title: "Reguły z YAML" },
  { id: "llm", color: "var(--acc-l)", icon: svg(<><rect x="6" y="6" width="12" height="12" rx="2" /><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" /></>), title: "LLM open-weight" },
  { id: "verify", color: "var(--ok-l)", icon: svg(<path d="M20 12a8 8 0 1 1-3-6.2M20 4v5h-5" />), title: "Weryfikacja i naprawa" },
  { id: "router", color: "var(--amber-l)", icon: svg(<path d="M4 18h6l4-12h6M14 18h6" />), title: "Router eskalacji" },
  { id: "vote", color: "var(--violet)", icon: svg(<><path d="M5 12l4 4L19 6" /><path d="M5 19h14" opacity=".5" /></>), title: "Głosowanie modeli" },
]

export function TierSlider() {
  const [i, setI] = useState(3)
  const t = TIERS[i]
  return (
    <section className="sec" id="suwak">
      <div className="wrap">
        <SectionHead eyebrow="Koszt i jakość" title="Płacisz tylko za trudne dokumenty." />
        <Reveal className="tier" style={{ "--gc": t.g, "--gx": t.x } as CSSProperties}>
          <div className="tends"><span>taniej</span><span>dokładniej</span></div>
          <div className="track">
            <div className="bar" />
            <div className="stops"><i /><i /><i /><i /><i /></div>
            <input
              type="range" min={0} max={4} step={1} value={i}
              aria-label="Profil przetwarzania" aria-valuetext={t.n}
              onChange={(e) => setI(Number(e.target.value))}
            />
          </div>
          <div className="tlabels">
            {TIERS.map((x, k) => (
              <button type="button" key={x.n} className={cn(k === i && "on")} onClick={() => setI(k)} aria-pressed={k === i}>
                {x.n}
              </button>
            ))}
          </div>
          <div className="tbody">
            <div>
              <div className="tname">{t.n}</div>
              <p className="tdesc">{t.d}</p>
              <div className="tfacts" key={i}>
                {t.f.map((x, k) => <span key={x} style={{ animationDelay: `${k * 60}ms` }}>{x}</span>)}
              </div>
            </div>
            <div className="comps">
              {COMPS.map((c) => (
                <div key={c.id} className={cn("comp", t.c.includes(c.id) && "on")} style={{ "--c": c.color } as CSSProperties}>
                  {c.icon}
                  <b>{c.title}</b>
                  <span className="sw" />
                </div>
              ))}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
