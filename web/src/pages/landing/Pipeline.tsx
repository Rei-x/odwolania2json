import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { SectionHead } from "./Reveal"

type Step = { name: string; title: string; body: ReactNode; tags?: string[] }

const STEPS: Step[] = [
  { name: "wejście", title: "PDF, skan albo zdjęcie", body: "Najpierw naprawiamy warstwę tekstową.", tags: ["pieczęć e-podpisu", "mojibake → UTF-8", "zepsuty font → OCR"] },
  { name: "orientacja", title: "Orientacja", body: "PP-LCNet prostuje obrócone strony." },
  { name: "ocr", title: "OCR", body: "Otwarty model wizyjny czyta skan." },
  { name: "klasyfikacja", title: "Klasyfikacja", body: <>Reguły, potem LLM. Dokument spoza zakresu dostaje <code className="mono">{"{}"}</code>.</> },
  { name: "ekstrakcja", title: "Ekstrakcja", body: "LLM z JSON Schema i przykładami few-shot." },
  { name: "normalizacja", title: "Normalizacja", body: "Deterministyczna, bez modelu.", tags: ["daty", "NIP · KRS", "IBAN", "BZP"] },
  { name: "dowody", title: "Weryfikacja i dowody", body: "Agent poprawia błędne pola. Każda wartość ma stronę i cytat." },
  { name: "sprawa", title: "Cała sprawa", body: "Kontrole krzyżowe między dokumentami." },
]
const pad = (n: number) => String(n).padStart(2, "0")

function StepBody({ i }: { i: number }) {
  const s = STEPS[i]
  return (
    <>
      <span className="n">{pad(i + 1)}</span>
      <h3>{s.title}</h3>
      <p>{s.body}</p>
      {s.tags && (
        <div className="tags">
          {s.tags.map((t) => <Badge variant="outline" className="bg-card font-mono" key={t}>{t}</Badge>)}
        </div>
      )}
    </>
  )
}

type Wire = { d: string; a: [number, number]; b: [number, number] }

export function Pipeline() {
  const [step, setStep] = useState(1)
  const [wire, setWire] = useState<Wire | null>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const qNipRef = useRef<HTMLSpanElement>(null)
  const jNipRef = useRef<HTMLDivElement>(null)
  const stepRefs = useRef<(HTMLDivElement | null)[]>([])

  // the step crossing the middle of the viewport drives the stage
  useEffect(() => {
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => { if (e.isIntersecting) setStep(Number((e.target as HTMLElement).dataset.s)) }),
      { rootMargin: "-48% 0px -48% 0px" },
    )
    stepRefs.current.forEach((el) => el && io.observe(el))
    return () => io.disconnect()
  }, [])

  // evidence wire from the NIP on the page to its JSON row
  useEffect(() => {
    if (step < 7) return
    const compute = () => {
      const st = stageRef.current, qa = qNipRef.current, jb = jNipRef.current
      if (!st || !qa || !jb) return
      const sr = st.getBoundingClientRect(), a = qa.getBoundingClientRect(), b = jb.getBoundingClientRect()
      if (!sr.width) return
      const x1 = a.right - sr.left + 4, y1 = a.top + a.height / 2 - sr.top, x2 = b.left - sr.left - 2, y2 = b.top + b.height / 2 - sr.top
      const mx = (x1 + x2) / 2
      if (x2 < x1 + 20) {
        const ax = a.left - sr.left + a.width / 2, ay = a.bottom - sr.top + 3, by = b.top - sr.top - 6, bx = b.left - sr.left + 40
        setWire({ d: `M${ax},${ay} C${ax},${by - 40} ${bx},${by - 40} ${bx},${by}`, a: [ax, ay], b: [bx, by] })
      } else {
        setWire({ d: `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`, a: [x1, y1], b: [x2, y2] })
      }
    }
    const raf = requestAnimationFrame(compute)
    window.addEventListener("resize", compute)
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", compute) }
  }, [step])

  const stageCls = ["stage", ...Array.from({ length: step }, (_, i) => `s${i + 1}`)].join(" ")

  return (
    <section className="sec pipeline" id="pipeline">
      <div className="wrap">
        <SectionHead eyebrow="Pipeline" title="Od skanu do dowodu." />
        <div className="pipe">
          <div className="stage-wrap">
            <div className={stageCls} ref={stageRef}>
              <div className="slabel"><b>{pad(step)}</b><span>{STEPS[step - 1].name}</span></div>
              <div className="sdoc">
                <div className="paper">
                  <div className="dl r">Poznań, dnia <span className="qq">11 września 2026 roku</span></div>
                  <div className="dl to">Prezes Krajowej Izby Odwoławczej</div>
                  <div className="dl"><span className="moj"><i className="bad">OdwoĹ‚ujÄ…cy:</i><i className="good">Odwołujący:</i></span> <b>Asterion Budownictwo sp. k.</b></div>
                  <div className="dl">KRS: 9991022552, <span className="qq g" ref={qNipRef}>NIP: 999-295-65-50</span></div>
                  <div className="dl">pełnomocnik: <span className="qq">radcę prawną Aleksandrę Rybak</span></div>
                  <div className="dl"><b>Zamawiający:</b> Powiatowy Zespół Szkół Technicznych</div>
                  <div className="dl">nr ref.: DA.ZP.242.50.2026, ogł. nr 2026/BZP 00767819/01</div>
                  <div className="ttl">ODWOŁANIE</div>
                  {[96, 88, 93, 62, 90, 95, 71, 84, 48].map((w, i) => <div className="ln" key={i} style={{ "--w": `${w}%` } as CSSProperties} />)}
                  <div className="stamp">WPŁYNĘŁO<small>dnia 11.09.2026</small></div>
                  <div className="esig">Podpisano elektronicznie<small>kwalifikowany podpis · adnotacja PDF</small></div>
                  <div className="noise" />
                  <div className="scan" />
                </div>
              </div>
              <div className="badge b-fix"><span className="d" />warstwa tekstowa <small>naprawiona</small></div>
              <div className="badge b-rot"><span className="d" />90° → 0° <small>PP-LCNet</small></div>
              <div className="badge b-cls"><span className="d" />odwołanie <small>reguły ✓ · LLM ✓</small></div>
              <div className="ghost"><span className="pg" /><span>wyrok_KIO.pdf<br /><small>spoza zakresu</small></span><b>{"{}"}</b></div>
              <div className="sjson">
                <div className="jh"><i /><i /><i /><span>odwolanie.json</span></div>
                <div className="jbr">{"{"}</div>
                <div className="jsk">
                  {[62, 84, 70, 90, 76, 66, 58].map((w, i) => <i key={i} style={{ "--w": `${w}%` } as CSSProperties} />)}
                </div>
                <div className="jr n"><span className="k">"data":</span><span className="v"><i className="raw">"11 września 2026 roku"</i><i className="norm">"2026-09-11"</i></span><span className="st" /></div>
                <div className="jr"><span className="k">"nazwa":</span><span className="v"><i className="raw s">"Asterion Budownictwo sp. k."</i></span><span className="st" /></div>
                <div className="jr n g" ref={jNipRef}><span className="k">"nip":</span><span className="v"><i className="raw">"999-295-65-50"</i><i className="norm">"9992956550"</i></span><span className="st" /></div>
                <div className="jr n"><span className="k">"pelnomocnik":</span><span className="v"><i className="raw">"radcę prawną Aleksandrę Rybak"</i><i className="norm">"Aleksandra Rybak"</i></span><span className="st" /></div>
                <div className="jr x"><span className="k">"numer_postepowania":</span><span className="v"><i className="raw">"DA.ZP.242.5<u>O</u>.2026"</i><i className="norm">"DA.ZP.242.50.2026"</i></span><span className="st" /></div>
                <div className="jr n"><span className="k">"numer_bzp":</span><span className="v"><i className="raw">"nr 2026/BZP 00767819/01"</i><i className="norm">"2026/BZP00767819/01"</i></span><span className="st" /></div>
                <div className="jr"><span className="k">"czynnosc_powod_id":</span><span className="v"><i className="raw">4</i></span><span className="st" /></div>
                <div className="jbr">{"}"}</div>
              </div>
              <div className="sprog">
                {STEPS.map((_, i) => <div key={i} className={cn(i < step && "on")}><i /><span>{pad(i + 1)}</span></div>)}
              </div>
              <svg className="wire" aria-hidden="true">
                <path d={wire?.d ?? ""} />
                <circle r="4" cx={wire?.a[0] ?? 0} cy={wire?.a[1] ?? 0} />
                <circle r="4" cx={wire?.b[0] ?? 0} cy={wire?.b[1] ?? 0} />
              </svg>
              <div className="pgl"><b>dowód</b> · str. 1<br />„NIP: 999-295-65-50”</div>
              <div className="case">
                <div className="cdocs">
                  <div className="cdoc" style={{ "--c": "var(--acc)" } as CSSProperties}><span className="pg" />odwołanie</div>
                  <span className="clink" />
                  <div className="cdoc" style={{ "--c": "var(--teal)" } as CSSProperties}><span className="pg" />pełnomocnictwo</div>
                  <span className="clink" />
                  <div className="cdoc" style={{ "--c": "var(--amber)" } as CSSProperties}><span className="pg" />przelew</div>
                </div>
                <div className="checks">
                  <div className="ck"><i>✓</i><span>NIP odwołującego = mocodawca pełnomocnictwa</span></div>
                  <div className="ck"><i>✓</i><span>Pełnomocnik z odwołania jest umocowany</span></div>
                  <div className="ck"><i>✓</i><span>Numer postępowania w tytule przelewu</span></div>
                  <div className="ck"><i>✓</i><span>Przelew nie później niż odwołanie</span></div>
                  <div className="ck"><i>✓</i><span>Kwota wpisu zgodna z rozporządzeniem</span></div>
                  <div className="ck fill"><i>↔</i><span>Brak uzupełniony z innego dokumentu<small>ze źródłem</small></span></div>
                </div>
              </div>
            </div>
            <div className="mcap" aria-live="polite">
              <div key={step}><StepBody i={step - 1} /></div>
            </div>
          </div>
          <div className="steps">
            <div className="rail"><i style={{ "--p": `${((step - 1) / (STEPS.length - 1)) * 100}%` } as CSSProperties} /></div>
            {STEPS.map((_, i) => (
              <div
                key={i}
                className={cn("step", step === i + 1 && "on")}
                data-s={i + 1}
                ref={(el) => { stepRefs.current[i] = el }}
              >
                <StepBody i={i} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
