import { useEffect, useState, type ReactNode } from "react"
import { prefersReducedMotion, useInViewOnce } from "./hooks"
import { Reveal } from "./Reveal"
import { ModelName } from "./VendorLogo"

const fmt = (v: number, d: number) => v.toFixed(d).replace(".", ",")

/** Number that counts up (ease-out quart, 1.5 s) the first time it is mostly visible. */
function CountUp({ to, dec, suffix }: { to: number; dec: number; suffix?: ReactNode }) {
  const [ref, seen] = useInViewOnce<HTMLElement>({ threshold: 0.6 })
  const [val, setVal] = useState(to)
  useEffect(() => {
    if (!seen || to === 0 || prefersReducedMotion()) return
    const t0 = performance.now(), dur = 1500, from = to > 50 ? 60 : 0
    let raf = 0
    const tick = (t: number) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 4)
      setVal(from + (to - from) * e)
      if (k < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [seen, to])
  return (
    <b ref={ref}>
      {fmt(val, dec)}
      {suffix && <small>{suffix}</small>}
    </b>
  )
}

const KPIS = [
  { to: 0.985, dec: 3, label: "F1 na ślepym zbiorze", note: <><ModelName vendor="mistral">Ministral 8B</ModelName> + Wróbelek</> },
  { to: 0.997, dec: 3, label: "F1 na danych UZP", note: <><ModelName vendor="anthropic">Opus 5.5</ModelName> = 1,000</> },
  { to: 2.7, dec: 1, suffix: "s", label: "mediana na dokument", note: "PDF cyfrowy, bez GPU" },
  { to: 929, dec: 0, label: "prawdziwych PDF-ów KIO", note: "ze 111 publicznych źródeł" },
]

export function Kpis() {
  return (
    <section className="band" id="liczby">
      <div className="wrap">
        <Reveal className="kpis">
          {KPIS.map((k) => (
            <div className="kpi" key={k.label}>
              <CountUp to={k.to} dec={k.dec} suffix={k.suffix} />
              <span>
                {k.label}
                <br />
                <em>{k.note}</em>
              </span>
            </div>
          ))}
        </Reveal>
      </div>
    </section>
  )
}
