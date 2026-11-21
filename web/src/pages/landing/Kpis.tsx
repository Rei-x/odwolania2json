import { useEffect, useState, type ReactNode } from "react"
import { prefersReducedMotion, useInViewOnce } from "./hooks"
import { Reveal } from "./Reveal"

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
  { to: 1, dec: 3, label: "F1 na danych UZP", note: "76 dokumentów" },
  { to: 0.999, dec: 3, label: "F1 na ślepym zbiorze", note: "20 nowych spraw" },
  { to: 98.3, dec: 1, suffix: "%", label: "trafna klasyfikacja", note: "116 trudnych przypadków" },
  { to: 0, dec: 0, suffix: "zł", label: "w trybie Reguły", note: "180 dokumentów w 2,9 s" },
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
