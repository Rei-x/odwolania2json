import { lazy, Suspense, useState, type CSSProperties, type Ref } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Flock } from "@/components/brand/flock"
import { SparrowMark } from "@/components/brand/logo"
import { ArrowIcon } from "./Reveal"
import type { SceneType } from "./HeroScene"

const HeroScene = lazy(() => import("./HeroScene"))

export function Hero({ ref }: { ref?: Ref<HTMLElement> }) {
  const [cap, setCap] = useState<SceneType>({ file: "odwolanie", col: "#c4551f" })
  return (
    <section className="hero" id="hero" ref={ref}>
      <div className="hcopy">
        <SparrowMark className="hero-bird" />
        <h1>
          <span className="l">Akta KIO → JSON.</span>
          <span className="l l3">Każda wartość z dowodem.</span>
        </h1>
        <p className="lede">Odwołanie, pełnomocnictwo i przelew w JSON‑ie zgodnym ze schematem UZP. Przy każdym polu strona i cytat.</p>
        <div className="ctas">
          <Button nativeButton={false} render={<Link to="/app" />} className="btn btn-p">
            Wypróbuj <ArrowIcon />
          </Button>
          <a className="btn btn-g" href="#wyprobuj">Trudne dokumenty</a>
        </div>
        <div className="trust">
          <span>F1 0,985 na ślepym zbiorze</span><span>modele 3–8B w UE</span><span>bez GPU</span><span>open source</span>
        </div>
      </div>
      <div className="hscene">
        <Flock />
        <Suspense fallback={null}>
          <HeroScene onType={setCap} />
        </Suspense>
        <div className="cap" aria-hidden="true" style={{ "--c": cap.col } as CSSProperties}>
          <span className="d" />
          <span>{cap.file}.pdf</span>
          <span className="ar">→</span>
          <b>{cap.file}.json</b>
        </div>
      </div>
      <a className="scroll-cue" href="#liczby"><i />przewiń</a>
    </section>
  )
}
