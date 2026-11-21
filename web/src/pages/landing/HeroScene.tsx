import { useEffect, useRef } from "react"
import { prefersReducedMotion } from "./hooks"

/* 3D hero: page → light beam → particles → JSON.
   Faithful port of the <script type="module"> from the legacy landing.html. three is
   imported lazily so first paint never waits for it. */

export type SceneType = { file: string; col: string }

type Tok = string | [string, "k" | "s" | "n" | "p"]
type DocType = {
  id: string
  title: string
  col: string
  file: string
  glow: string
  json: Tok[][]
}

const TYPES: DocType[] = [
  { id: "odwolanie", title: "ODWOŁANIE", col: "#c4551f", glow: "#e88a4f", file: "odwolanie",
    json: [["{"], ["  ", ['"Odwolujacy"', "k"], ": {"], ["    ", ['"nip"', "k"], ": ", ['"9992956550"', "s"]], ["  },"], ["  ", ['"data"', "k"], ": ", ['"2026-09-11"', "s"]], ["}"]] },
  { id: "pelnomocnictwo", title: "PEŁNOMOCNICTWO", col: "#5b7d47", glow: "#9cbf7f", file: "pelnomocnictwo",
    json: [["{"], ["  ", ['"pelnomocnicy"', "k"], ": ["], ["    ", ['"Aleksandra Rybak"', "s"]], ["  ],"], ["  ", ['"typ"', "k"], ": ", ['"osoba_prawna"', "s"]], ["}"]] },
  { id: "przelew", title: "POTWIERDZENIE PRZELEWU", col: "#b07a24", glow: "#e7b75c", file: "potwierdzenie_przelewu",
    json: [["{"], ["  ", ['"przelew_bankowy"', "k"], ": {"], ["    ", ['"kwota"', "k"], ": ", ["15000.00", "n"], ","], ["    ", ['"data_operacji"', "k"], ": ", ['"2026-09-10"', "s"]], ["  }"], ["}"]] },
]
const JSONCOL = { k: "#ffffff", s: "#9cbf7f", n: "#e7b75c", p: "#e88a4f" }
const SANS = '"Inter Variable", Inter, sans-serif'
const MONO = '"JetBrains Mono Variable", monospace'

// page textures
const PW = 512, PH = 724, TS = 2

function drawPage(t: DocType) {
  let seed = t.id.length * 97 + 11
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647
  const c = document.createElement("canvas")
  c.width = PW * TS
  c.height = PH * TS
  const g = c.getContext("2d")!
  g.scale(TS, TS)
  g.fillStyle = "#f6f4ef"; g.fillRect(0, 0, PW, PH)
  g.fillStyle = t.col; g.fillRect(44, 46, 70, 9)
  g.fillStyle = "#d0cac4"; g.fillRect(PW - 44 - 130, 48, 130, 6)
  g.fillStyle = "#2b211b"; g.font = `800 ${t.title.length > 16 ? 25 : 32}px ${SANS}`; g.textAlign = "center"; g.fillText(t.title, PW / 2, 128)
  let y = 172
  const line = (x: number, w: number, h: number, col: string) => { g.fillStyle = col; g.beginPath(); g.roundRect(x, y, w, h, h / 2); g.fill() }
  if (t.id === "przelew") {
    for (let r = 0; r < 6; r++) {
      g.strokeStyle = "#dcd8d3"; g.lineWidth = 2; g.strokeRect(44, y - 10, PW - 88, 58)
      line(58, 90 + rnd() * 50, 7, "#b9b0a7"); y += 22; line(58, 160 + rnd() * 200, 9, r === 2 ? t.col : "#5e4c40"); y += 44
    }
    y += 26; g.fillStyle = t.col; g.strokeStyle = t.col; g.lineWidth = 3; g.strokeRect(PW - 200, y, 150, 40)
    g.font = `800 17px ${SANS}`; g.fillText("ZREALIZOWANO", PW - 125, y + 27)
  } else {
    for (let p = 0; p < 5; p++) {
      const n = 2 + ((rnd() * 3) | 0)
      for (let i = 0; i < n; i++) { const w = i === n - 1 ? 140 + rnd() * 200 : PW - 88 - rnd() * 40; line(44, w, 8, p === 0 && i < 2 ? "#5e4c40" : "#b8afa6"); y += 21 }
      y += 16
    }
    if (t.id === "pelnomocnictwo") {
      g.strokeStyle = t.col; g.lineWidth = 4; g.beginPath(); g.arc(PW - 140, PH - 140, 54, 0, Math.PI * 2); g.stroke()
      g.lineWidth = 2; g.beginPath(); g.arc(PW - 140, PH - 140, 40, 0, Math.PI * 2); g.stroke()
    } else {
      g.strokeStyle = "rgba(122,79,46,.8)"; g.lineWidth = 3; g.save(); g.translate(120, PH - 110); g.rotate(-0.1); g.strokeRect(-70, -26, 140, 52)
      g.fillStyle = "rgba(122,79,46,.8)"; g.font = `800 18px ${SANS}`; g.fillText("WPŁYNĘŁO", 0, 6); g.restore()
    }
    g.strokeStyle = "#2b211b"; g.lineWidth = 2.5; g.beginPath(); const sx = PW - 230; g.moveTo(sx, PH - 70)
    for (let i = 0; i < 14; i++) g.quadraticCurveTo(sx + i * 9 + 4, PH - 70 - 26 * (i % 2 ? 1 : -0.6) * rnd(), sx + i * 9 + 9, PH - 70)
    g.stroke()
  }
  return c
}

function samplePage(c: HTMLCanvasElement) {
  const W = c.width, H = c.height
  const d = c.getContext("2d")!.getImageData(0, 0, W, H).data
  const ink: number[] = [], paper: number[] = []
  for (let y = 0; y < H; y += 4)
    for (let x = 0; x < W; x += 4) {
      const i = (y * W + x) * 4, l = (d[i] + d[i + 1] + d[i + 2]) / 3
      ;(l < 215 ? ink : paper).push(x / W, y / H, d[i] / 255, d[i + 1] / 255, d[i + 2] / 255)
    }
  return { ink, paper }
}

function sampleJSON(t: DocType) {
  const c = document.createElement("canvas"), W = 1100, LH = 74, FS = 54
  c.width = W; c.height = LH * t.json.length + 40
  const g = c.getContext("2d")!
  g.font = `700 ${FS}px ${MONO}`; g.textBaseline = "top"
  const cw = g.measureText("M").width
  t.json.forEach((row, r) => {
    let x = 10
    row.forEach((tok) => {
      const [txt, kind] = typeof tok === "string" ? [tok, "p" as const] : tok
      for (const ch of txt) {
        g.fillStyle = kind === "p" ? (/[{}[\]:,]/.test(ch) ? JSONCOL.p : "#fff") : JSONCOL[kind]
        g.fillText(ch, x, 20 + r * LH); x += cw
      }
    })
  })
  const d = g.getImageData(0, 0, c.width, c.height).data, pts: number[] = []
  let minx = 1e9, maxx = 0, miny = 1e9, maxy = 0
  for (let y = 0; y < c.height; y += 2)
    for (let x = 0; x < W; x += 2) {
      const i = (y * W + x) * 4
      if (d[i + 3] > 140) {
        pts.push(x, y, d[i] / 255, d[i + 1] / 255, d[i + 2] / 255)
        minx = Math.min(minx, x); maxx = Math.max(maxx, x); miny = Math.min(miny, y); maxy = Math.max(maxy, y)
      }
    }
  return { pts, minx, maxx, miny, maxy }
}

const VERT_UV = "varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }"

export default function HeroScene({ onType }: { onType: (t: SceneType) => void }) {
  const hostRef = useRef<HTMLDivElement>(null)
  const onTypeRef = useRef(onType)
  useEffect(() => { onTypeRef.current = onType }, [onType])

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    let disposed = false
    const cleanups: (() => void)[] = []

    ;(async () => {
      const THREE = await import("three")
      if (disposed) return
      await Promise.all([document.fonts.load(`800 40px "Inter Variable"`), document.fonts.load(`700 40px "JetBrains Mono Variable"`)]).catch(() => {})
      if (disposed) return

      const RM = prefersReducedMotion()
      const canvas = document.createElement("canvas")
      canvas.setAttribute("aria-hidden", "true")
      let renderer: InstanceType<typeof THREE.WebGLRenderer>
      try {
        renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" })
      } catch {
        return // no WebGL: the hero copy and gradient still stand on their own
      }
      host.appendChild(canvas)
      const disposables: { dispose(): void }[] = []
      const track = <T extends { dispose(): void }>(o: T) => (disposables.push(o), o)
      cleanups.push(() => {
        disposables.forEach((d) => d.dispose())
        renderer.dispose()
        renderer.forceContextLoss()
        canvas.remove()
      })

      const PR = Math.min(window.devicePixelRatio || 1, 1.75)
      renderer.setPixelRatio(PR)
      renderer.setClearColor(0x000000, 0)

      const scene = new THREE.Scene()
      const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100)
      const world = new THREE.Group()
      scene.add(world)

      const types = TYPES.map((t) => {
        const cv = drawPage(t)
        const tex = track(new THREE.CanvasTexture(cv))
        tex.colorSpace = THREE.SRGBColorSpace
        tex.anisotropy = 4
        return { ...t, tex, samp: samplePage(cv), js: sampleJSON(t) }
      })

      // page mesh
      const PAGE_W = 2.7, PAGE_H = (PAGE_W * PH) / PW
      const pageGroup = new THREE.Group()
      world.add(pageGroup)
      const pageMat = track(new THREE.ShaderMaterial({
        transparent: true, depthWrite: false,
        uniforms: { map: { value: types[0].tex }, uSweep: { value: 0 }, uAlpha: { value: 0 }, uGlow: { value: new THREE.Color("#e88a4f") } },
        vertexShader: VERT_UV,
        fragmentShader: `uniform sampler2D map; uniform float uSweep, uAlpha; uniform vec3 uGlow; varying vec2 vUv;
          void main(){ float d = vUv.x - uSweep; if (d < 0. || uSweep > .995) discard;
            vec4 c = texture2D(map, vUv); float e = smoothstep(.07, 0., d) * step(.001, uSweep);
            vec3 col = mix(c.rgb, uGlow * 1.6, e * .9);
            float vig = smoothstep(0., .02, vUv.y) * smoothstep(1., .98, vUv.y);
            gl_FragColor = vec4(col, uAlpha * vig); }`,
      }))
      const page = new THREE.Mesh(track(new THREE.PlaneGeometry(PAGE_W, PAGE_H)), pageMat)
      pageGroup.add(page)
      // soft glow behind page
      const glowTex = track((() => {
        const c = document.createElement("canvas"); c.width = c.height = 128
        const g = c.getContext("2d")!
        const gr = g.createRadialGradient(64, 64, 0, 64, 64, 64)
        gr.addColorStop(0, "rgba(255,255,255,1)"); gr.addColorStop(1, "rgba(255,255,255,0)")
        g.fillStyle = gr; g.fillRect(0, 0, 128, 128)
        return new THREE.CanvasTexture(c)
      })())
      const haloMat = track(new THREE.MeshBasicMaterial({ map: glowTex, color: "#c4551f", transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false }))
      const halo = new THREE.Mesh(track(new THREE.PlaneGeometry(PAGE_W * 2.1, PAGE_H * 1.6)), haloMat)
      halo.position.z = -0.3
      pageGroup.add(halo)
      // beam
      const beamMat = track(new THREE.ShaderMaterial({
        transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
        uniforms: { uA: { value: 0 }, uTime: { value: 0 } },
        vertexShader: VERT_UV,
        fragmentShader: `uniform float uA, uTime; varying vec2 vUv;
          void main(){ float x = abs(vUv.x - .5) * 2.; float core = exp(-x * x * 900.); float glow = exp(-x * 7.) * .55;
            float yv = smoothstep(0., .12, vUv.y) * smoothstep(1., .88, vUv.y);
            float fl = .85 + .15 * sin(uTime * 30. + vUv.y * 40.);
            vec3 col = vec3(1.) * core + vec3(1., .25, .5) * glow;
            vec3 o = col * yv * uA * fl; gl_FragColor = vec4(o, max(o.r, max(o.g, o.b))); }`,
      }))
      const beam = new THREE.Mesh(track(new THREE.PlaneGeometry(1.4, PAGE_H * 1.25)), beamMat)
      beam.position.z = 0.05
      pageGroup.add(beam)

      // particles
      const small = window.innerWidth < 760
      const N = small ? 8000 : 15000
      const geo = track(new THREE.BufferGeometry())
      const aStart = new Float32Array(N * 3), aEnd = new Float32Array(N * 3), aU = new Float32Array(N), aSeed = new Float32Array(N), aCol = new Float32Array(N * 3), aSCol = new Float32Array(N * 3)
      for (let i = 0; i < N; i++) aSeed[i] = Math.random()
      geo.setAttribute("position", new THREE.BufferAttribute(aEnd, 3))
      geo.setAttribute("aStart", new THREE.BufferAttribute(aStart, 3))
      geo.setAttribute("aEnd", new THREE.BufferAttribute(aEnd, 3))
      geo.setAttribute("aU", new THREE.BufferAttribute(aU, 1))
      geo.setAttribute("aSeed", new THREE.BufferAttribute(aSeed, 1))
      geo.setAttribute("aCol", new THREE.BufferAttribute(aCol, 3))
      geo.setAttribute("aSCol", new THREE.BufferAttribute(aSCol, 3))
      const ptsMat = track(new THREE.ShaderMaterial({
        transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
        uniforms: { uClock: { value: 0 }, uSweepDur: { value: 1.3 }, uFly: { value: 0.8 }, uOut: { value: 0 }, uTime: { value: 0 }, uSize: { value: small ? 2.1 : 2.0 }, uPR: { value: PR }, uType: { value: new THREE.Color("#c4551f") } },
        vertexShader: `attribute vec3 aStart, aEnd, aCol, aSCol; attribute float aU, aSeed;
          uniform float uClock, uSweepDur, uFly, uOut, uTime, uSize, uPR; uniform vec3 uType;
          varying vec3 vCol; varying float vA;
          float ease(float t){ return t < .5 ? 4.*t*t*t : 1. - pow(-2.*t + 2., 3.) / 2.; }
          void main(){
            float tEmit = aU * uSweepDur + aSeed * .1;
            float p = clamp((uClock - tEmit) / (uFly * (.75 + aSeed * .6)), 0., 1.);
            float e = ease(p);
            vec3 mid = mix(aStart, aEnd, .45) + vec3(0., (aSeed - .5) * 2.4, 1.2 + aSeed * 1.8);
            vec3 pos = mix(mix(aStart, mid, e), mix(mid, aEnd, e), e);
            float fl = sin(p * 3.14159);
            pos += fl * vec3(sin(uTime * 2.1 + aSeed * 40.) * .22, cos(uTime * 1.7 + aSeed * 31.) * .22, sin(uTime + aSeed * 9.) * .2);
            pos.y += step(.999, p) * sin(uTime * 1.6 + aEnd.x * 1.3 + aSeed * .6) * .012;
            pos += uOut * uOut * vec3((aSeed - .5) * 4., .8 + aSeed * 2.5, (aSeed - .2) * 5.);
            vec4 mv = modelViewMatrix * vec4(pos, 1.);
            gl_Position = projectionMatrix * mv;
            float vis = step(.0001, p);
            gl_PointSize = uSize * uPR * (1. + fl * 1.8) * (12. / -mv.z) * vis;
            vec3 hot = mix(aSCol, uType * 1.5 + .25, .6);
            vCol = mix(hot, aCol, smoothstep(.5, 1., p));
            vA = vis * (1. - uOut) * (.7 + .3 * fl);
          }`,
        fragmentShader: `varying vec3 vCol; varying float vA;
          void main(){ vec2 q = gl_PointCoord - .5; float d = length(q); if (d > .5) discard; float a = smoothstep(.5, .05, d);
            gl_FragColor = vec4(vCol * (1. + smoothstep(.2, 0., d) * .6), a * vA); }`,
      }))
      const particles = new THREE.Points(geo, ptsMat)
      particles.frustumCulled = false
      world.add(particles)

      // dust
      const DN = small ? 260 : 520, dgeo = track(new THREE.BufferGeometry()), dpos = new Float32Array(DN * 3)
      for (let i = 0; i < DN; i++) { dpos[i * 3] = (Math.random() - 0.5) * 22; dpos[i * 3 + 1] = (Math.random() - 0.5) * 14; dpos[i * 3 + 2] = -Math.random() * 10 - 1 }
      dgeo.setAttribute("position", new THREE.BufferAttribute(dpos, 3))
      const dust = new THREE.Points(dgeo, track(new THREE.PointsMaterial({ size: 0.045, color: "#c4dbaf", transparent: true, opacity: 0.45, depthWrite: false, blending: THREE.AdditiveBlending, map: glowTex })))
      scene.add(dust)

      // layout
      const L = { page: new THREE.Vector3(), json: new THREE.Vector3(), jw: 4, vertical: false }
      function layout() {
        const w = host!.clientWidth, h = host!.clientHeight
        if (!w || !h) return
        renderer.setSize(w, h, false)
        camera.aspect = w / h
        L.vertical = camera.aspect < 1.3 // diagonal composition: page top-left, JSON bottom-right
        const tan = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))
        let halfW: number, halfH: number
        if (L.vertical) { L.page.set(-1.6, 1.3, 0); L.json.set(0.7, -2.15, 0); L.jw = 4.5; halfW = 3.5; halfH = 4.55 }
        else { L.page.set(-2.85, 0.1, 0); L.json.set(2.35, 0.05, 0); L.jw = 4.6; halfW = 5.0; halfH = 2.75 }
        pageGroup.scale.setScalar(1)
        camera.position.set(0, 0, Math.max(halfH / tan, halfW / (tan * camera.aspect)))
        camera.updateProjectionMatrix()
      }

      // cycle: the next page flies in while the previous JSON dissolves; particles re-target when the sweep starts
      let ti = -1, cycleT = 0, hasOld = false, armed = false
      // ~4.6 s per document (was ~8.9 s): faster fly-in, sweep and particle flight, shorter hold
      const T_IN = 0.6, T_SW = 0.75, SWEEP = 1.3, HOLD = 1.4, OUT = 0.55
      const T_LAND = T_SW + SWEEP + 0.1 + 0.8 * 1.35
      const CYCLE = T_LAND + HOLD
      const pageRotY = () => (L.vertical ? 0.26 : 0.32)
      function nextPage() {
        ti = (ti + 1) % types.length
        const t = types[ti]
        pageMat.uniforms.map.value = t.tex
        haloMat.color.set(t.col)
        pageMat.uniforms.uGlow.value.set(t.glow)
        onTypeRef.current({ file: t.file, col: t.col })
        armed = false
      }
      const m = new THREE.Matrix4(), v = new THREE.Vector3()
      function setParticles() {
        const t = types[ti]
        armed = true; hasOld = true
        ptsMat.uniforms.uType.value.set(t.col)
        pageGroup.position.copy(L.page); pageGroup.rotation.set(-0.04, pageRotY(), L.vertical ? -0.04 : 0.02); pageGroup.updateMatrix()
        m.multiplyMatrices(pageGroup.matrix, page.matrix)
        const { ink, paper } = t.samp, js = t.js, sx = L.jw / (js.maxx - js.minx), cx = (js.minx + js.maxx) / 2, cy = (js.miny + js.maxy) / 2
        const nj = js.pts.length / 5
        for (let i = 0; i < N; i++) {
          const usePaper = Math.random() < 0.16, src = usePaper ? paper : ink, k = ((Math.random() * (src.length / 5)) | 0) * 5
          const u = src[k], vv = src[k + 1]
          v.set((u - 0.5) * PAGE_W, (0.5 - vv) * PAGE_H, 0).applyMatrix4(m)
          aStart[i * 3] = v.x; aStart[i * 3 + 1] = v.y; aStart[i * 3 + 2] = v.z; aU[i] = u
          aSCol[i * 3] = usePaper ? 0.9 : src[k + 2]; aSCol[i * 3 + 1] = usePaper ? 0.9 : src[k + 3]; aSCol[i * 3 + 2] = usePaper ? 0.95 : src[k + 4]
          const j = ((Math.random() * nj) | 0) * 5
          aEnd[i * 3] = L.json.x + (js.pts[j] - cx) * sx; aEnd[i * 3 + 1] = L.json.y - (js.pts[j + 1] - cy) * sx; aEnd[i * 3 + 2] = L.json.z + (Math.random() - 0.5) * 0.06
          aCol[i * 3] = js.pts[j + 2]; aCol[i * 3 + 1] = js.pts[j + 3]; aCol[i * 3 + 2] = js.pts[j + 4]
        }
        for (const n of ["aStart", "aEnd", "aU", "aCol", "aSCol"]) geo.attributes[n].needsUpdate = true
      }
      const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
      function update(t: number, time: number) {
        const pu = pageMat.uniforms, U = ptsMat.uniforms
        U.uTime.value = time; beamMat.uniforms.uTime.value = time
        // page fly-in
        const kin = ease(Math.min(1, t / T_IN))
        pageGroup.position.set(L.page.x - (1 - kin) * 4.5, L.page.y + (1 - kin) * 0.8, L.page.z - (1 - kin) * 6)
        pageGroup.rotation.set(-0.04, pageRotY() + (1 - kin) * 1.1, L.vertical ? -0.04 : 0.02)
        pu.uAlpha.value = kin
        const sw = Math.min(1, Math.max(0, (t - T_SW) / SWEEP))
        haloMat.opacity = 0.18 * kin * (1 - sw)
        pu.uSweep.value = sw
        beam.position.x = (sw - 0.5) * PAGE_W
        beamMat.uniforms.uA.value = t < T_SW ? Math.max(0, (t - (T_SW - 0.25)) / 0.25) : sw < 1 ? 1 : Math.max(0, 1 - (t - T_SW - SWEEP) / 0.2)
        // particles: previous JSON dissolves during the fly-in, then the new page streams in
        if (t >= T_SW && !armed) setParticles()
        if (armed) { U.uClock.value = t - T_SW; U.uOut.value = 0 }
        else { U.uClock.value = 99; U.uOut.value = hasOld ? Math.min(1, t / OUT) : 1 }
      }

      // interaction + loop
      const mouse = { x: 0, y: 0, tx: 0, ty: 0 }
      const onPointer = (e: PointerEvent) => { mouse.tx = e.clientX / window.innerWidth - 0.5; mouse.ty = e.clientY / window.innerHeight - 0.5 }
      window.addEventListener("pointermove", onPointer, { passive: true })
      cleanups.push(() => window.removeEventListener("pointermove", onPointer))

      let visible = true, running = false, raf = 0, last = performance.now(), time = 0
      function frame(now: number) {
        if (!visible || document.hidden) { running = false; return }
        const dt = Math.min(0.05, (now - last) / 1000)
        last = now; time += dt; cycleT += dt
        if (cycleT > CYCLE) { cycleT = 0; nextPage() }
        update(cycleT, time)
        mouse.x += (mouse.tx - mouse.x) * 0.04; mouse.y += (mouse.ty - mouse.y) * 0.04
        world.rotation.y = mouse.x * 0.16; world.rotation.x = mouse.y * 0.08
        dust.rotation.y = time * 0.01; dust.position.y = Math.sin(time * 0.2) * 0.2
        renderer.render(scene, camera)
        raf = requestAnimationFrame(frame)
      }
      function start() {
        if (running || RM || disposed) return
        running = true; last = performance.now(); raf = requestAnimationFrame(frame)
      }
      function still() { // reduced motion: one composed frame (intact page + assembled JSON)
        if (!armed) setParticles()
        update(T_LAND + 0.5, 0); pageMat.uniforms.uSweep.value = 0; beamMat.uniforms.uA.value = 0; haloMat.opacity = 0.15
        ptsMat.uniforms.uClock.value = 99; renderer.render(scene, camera)
      }
      cleanups.push(() => cancelAnimationFrame(raf))

      layout(); nextPage()
      const ro = new ResizeObserver(() => { layout(); if (armed) setParticles(); if (RM) still() })
      ro.observe(host)
      const io = new IntersectionObserver((es) => { visible = es[0].isIntersecting; if (visible) start() }, { threshold: 0.02 })
      io.observe(host)
      const onVis = () => { if (!document.hidden) start() }
      document.addEventListener("visibilitychange", onVis)
      cleanups.push(() => { ro.disconnect(); io.disconnect(); document.removeEventListener("visibilitychange", onVis) })
      if (RM) still()
      else start()
    })()

    return () => {
      disposed = true
      cleanups.forEach((f) => f())
    }
  }, [])

  return <div ref={hostRef} className="absolute inset-0" />
}
