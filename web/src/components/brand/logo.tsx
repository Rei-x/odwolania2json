import { cn } from "@/lib/utils"

/** House sparrow mark (perched male: chestnut crown, black mask and bib, cream cheek). */
export function SparrowMark({ className }: { className?: string }) {
  return (
    <svg viewBox="18 20 172 176" aria-hidden="true" className={cn("size-7 shrink-0", className)}>
      <path d="M78 136 L28 186 C24 191 30 196 35 192 L92 146Z" fill="#8f3f24"/>
      <path d="M84 138 L40 182" stroke="#6e2f1a" strokeWidth="1.6" strokeLinecap="round"/>
      <path d="M128 146 L120 176 M138 146 L140 178" stroke="#8a2f2a" strokeWidth="4" strokeLinecap="round"/>
      <path d="M110 178 L130 177 M132 180 L152 180" stroke="#8a2f2a" strokeWidth="4" strokeLinecap="round"/>
      <path d="M78 142 C68 112 80 78 110 62 C132 52 158 58 168 82 C176 108 164 136 138 148 C118 156 92 156 78 142Z" fill="#ecdab6"/>
      <path d="M150 70 C166 84 170 110 160 130 C152 140 142 146 130 150 C150 136 160 112 150 70Z" fill="#dcc396"/>
      <path d="M64 150 C56 118 70 84 102 70 C122 62 140 70 142 88 C144 110 130 132 104 144 C88 151 74 154 64 150Z" fill="#9b4628"/>
      <path d="M72 148 C82 132 98 122 118 116 C110 132 96 142 80 150Z" fill="#7d351d"/>
      <g fill="#2a1d16">
      <path d="M104 82 q6 -6 12 0 q-6 -2 -12 0z"/><path d="M118 80 q6 -6 12 0 q-6 -2 -12 0z"/>
      <path d="M96 92 q6 -6 12 0 q-6 -2 -12 0z"/><path d="M110 92 q6 -6 12 0 q-6 -2 -12 0z"/><path d="M124 91 q6 -6 12 0 q-6 -2 -12 0z"/>
      <path d="M100 103 q6 -6 12 0 q-6 -2 -12 0z"/><path d="M114 103 q6 -6 12 0 q-6 -2 -12 0z"/>
      </g>
      <path d="M86 118 q5 4 10 0 M98 116 q5 4 10 0 M110 113 q5 4 10 0 M80 130 q5 4 10 0 M92 128 q5 4 10 0" stroke="#f3e2c0" strokeWidth="1.8" fill="none" strokeLinecap="round"/>
      <path d="M116 52 C116 35 131 25 148 26 C164 27 172 40 170 54 C168 64 162 70 154 72 C140 70 128 68 120 64 C117 60 116 56 116 52Z" fill="#a04d2c"/>
      <path d="M122 56 C122 70 128 82 138 88 C148 92 158 88 164 80 C168 72 169 64 168 56 C152 60 136 60 122 56Z" fill="#efe0c2"/>
      <path d="M128 52 C140 45 156 43 169 46 L169 54 C158 53 146 55 134 59 C131 57 129 55 128 52Z" fill="#231915"/><path d="M160 56 C166 60 167 70 162 82 C158 86 152 86 149 82 C154 76 157 66 160 56Z" fill="#231915"/>
      <circle cx="153" cy="49" r="5" fill="#231915" stroke="#f7efe2" strokeWidth="1.6"/><circle cx="151.5" cy="47.5" r="1.3" fill="#fff"/>
      <path d="M168 46 L186 52 L168 58 C166 54 166 50 168 46Z" fill="#a8988d"/><path d="M168 52 L186 52 L168 58Z" fill="#8c7d72"/>
    </svg>
  )
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-extrabold tracking-tight", className)}>
      <SparrowMark />
      <span>
        Wróbel<span className="text-primary">ek</span>
      </span>
    </span>
  )
}
