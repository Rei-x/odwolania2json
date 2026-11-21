import { lazy, Suspense, useState, type CSSProperties, type Ref } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Flock } from "@/components/brand/flock"
import { ArrowIcon } from "./Reveal"
import type { SceneType } from "./HeroScene"

const HeroScene = lazy(() => import("./HeroScene"))

export function Hero({ ref }: { ref?: Ref<HTMLElement> }) {
  const [cap, setCap] = useState<SceneType>({ file: "odwolanie", col: "#c4551f" })
  return (
    <section className="hero" id="hero" ref={ref}>
      <div className="hcopy">
        <span className="eyebrow">Odwołanie · pełnomocnictwo · przelew</span>
        <h1>
          <span className="l">Skan wchodzi.</span>
          <span className="l">JSON wychodzi.</span>
          <span className="l l3">Każde pole z dowodem.</span>
        </h1>
        <p className="lede">Akta odwołania do KIO zamienione na dane zgodne ze schematem UZP. Przy każdej wartości strona i cytat.</p>
        <div className="ctas">
          <Button nativeButton={false} render={<Link to="/app" />} className="btn btn-p">
            Wypróbuj <ArrowIcon />
          </Button>
          <a className="btn btn-g" href="#wyprobuj">Trudne dokumenty</a>
        </div>
        <div className="trust">
          <span>F1 1,000 na danych UZP</span><span>open-weight</span><span>hosting w UE</span><span>CPU</span>
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
