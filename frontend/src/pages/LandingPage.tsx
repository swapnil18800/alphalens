import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ArrowRight, Search, Zap, Globe, ShieldCheck,
  GitBranch, RefreshCw, Info, LogIn, ArrowUp,
} from 'lucide-react'
import AboutModal from '../components/AboutModal'
import AuthModal from '../components/AuthModal'
import { AUTH_AVAILABLE } from '../lib/config'
import { useAuthStatus } from '../hooks/useAuthStatus'

// ──────────────────────────────────────────────────────────────────────────
// Geometric hero animation — randomly placed rotating polygons + grid
// ──────────────────────────────────────────────────────────────────────────

function GeometricBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animId: number

    type Poly = { cx: number; cy: number; r: number; sides: number; rot: number; speed: number; alpha: number }
    let polys: Poly[] = []

    const initPolys = (w: number, h: number) => {
      polys = Array.from({ length: 18 }, () => ({
        cx:    Math.random() * w,
        cy:    Math.random() * h,
        r:     Math.random() * 85 + 40,
        sides: [3, 4, 6, 8][Math.floor(Math.random() * 4)],
        rot:   Math.random() * Math.PI * 2,
        speed: (Math.random() - 0.5) * 0.009,
        alpha: Math.random() * 0.07 + 0.03,
      }))
    }

    const resize = () => {
      const p = canvas.parentElement
      if (!p) return
      canvas.width  = p.offsetWidth
      canvas.height = p.offsetHeight
      if (polys.length === 0) initPolys(canvas.width, canvas.height)
    }

    resize()
    const ro = new ResizeObserver(() => resize())
    if (canvas.parentElement) ro.observe(canvas.parentElement)
    window.addEventListener('resize', resize)

    const drawPoly = (p: Poly) => {
      ctx.beginPath()
      for (let i = 0; i < p.sides; i++) {
        const a = p.rot + (i * Math.PI * 2) / p.sides
        const x = p.cx + Math.cos(a) * p.r
        const y = p.cy + Math.sin(a) * p.r
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
      }
      ctx.closePath()
      ctx.strokeStyle = `rgba(0,0,0,${p.alpha + 0.12})`
      ctx.lineWidth = 1
      ctx.stroke()
      ctx.fillStyle = `rgba(0,0,0,${p.alpha})`
      ctx.fill()
    }

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      ctx.strokeStyle = 'rgba(0,0,0,0.035)'
      ctx.lineWidth = 1
      const step = 60
      for (let x = 0; x < canvas.width; x += step) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke()
      }
      for (let y = 0; y < canvas.height; y += step) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke()
      }
      for (const p of polys) {
        drawPoly(p)
        p.rot += p.speed
        p.cx  += Math.cos(p.rot) * 0.4
        p.cy  += Math.sin(p.rot) * 0.4
        if (p.cx < -120) p.cx = canvas.width  + 120
        if (p.cx > canvas.width  + 120) p.cx = -120
        if (p.cy < -120) p.cy = canvas.height + 120
        if (p.cy > canvas.height + 120) p.cy = -120
      }
      animId = requestAnimationFrame(draw)
    }
    draw()

    return () => { cancelAnimationFrame(animId); ro.disconnect(); window.removeEventListener('resize', resize) }
  }, [])

  return <canvas ref={canvasRef} className="absolute inset-0 w-full h-full pointer-events-none" />
}

// ──────────────────────────────────────────────────────────────────────────
// Section transition — gradient fade that bridges background colour changes
// ──────────────────────────────────────────────────────────────────────────

function SectionTransition({ from = 'white', to = '#f5f5f5' }: { from?: string; to?: string }) {
  return (
    <div
      className="w-full h-16 pointer-events-none"
      style={{ background: `linear-gradient(to bottom, ${from}, ${to})` }}
    />
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Smooth infinite ticker with JS animation + mouse drag
// ──────────────────────────────────────────────────────────────────────────

function useInfiniteTicker(pixelsPerFrame = 0.7) {
  const trackRef = useRef<HTMLDivElement>(null)
  const posRef   = useRef(0)
  const rafRef   = useRef<number>(0)
  const dragRef  = useRef(false)
  const lastXRef = useRef(0)

  useEffect(() => {
    const track = trackRef.current
    if (!track) return

    const tick = () => {
      if (!dragRef.current) {
        posRef.current -= pixelsPerFrame
        const half = track.scrollWidth / 2
        if (posRef.current <= -half) posRef.current += half
        if (posRef.current > 0) posRef.current -= half
        track.style.transform = `translateX(${posRef.current}px)`
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)

    const onDown = (e: MouseEvent) => {
      dragRef.current = true
      lastXRef.current = e.clientX
      document.body.style.cursor = 'grabbing'
    }
    const onMove = (e: MouseEvent) => {
      if (!dragRef.current) return
      posRef.current += e.clientX - lastXRef.current
      lastXRef.current = e.clientX
      const half = track.scrollWidth / 2
      if (posRef.current <= -half) posRef.current += half
      if (posRef.current > 0) posRef.current -= half
      track.style.transform = `translateX(${posRef.current}px)`
    }
    const onUp = () => { dragRef.current = false; document.body.style.cursor = '' }

    const wrapper = track.parentElement
    wrapper?.addEventListener('mousedown', onDown)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)

    return () => {
      cancelAnimationFrame(rafRef.current)
      wrapper?.removeEventListener('mousedown', onDown)
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [pixelsPerFrame])

  return trackRef
}

// ──────────────────────────────────────────────────────────────────────────
// Coverage universe
// ──────────────────────────────────────────────────────────────────────────

const COMPANIES = [
  { t: 'AAPL',  n: 'Apple' },
  { t: 'ADBE',  n: 'Adobe' },
  { t: 'AMD',   n: 'AMD' },
  { t: 'AMZN',  n: 'Amazon' },
  { t: 'AVGO',  n: 'Broadcom' },
  { t: 'CRM',   n: 'Salesforce' },
  { t: 'CSCO',  n: 'Cisco' },
  { t: 'GOOGL', n: 'Alphabet' },
  { t: 'IBM',   n: 'IBM' },
  { t: 'INTC',  n: 'Intel' },
  { t: 'META',  n: 'Meta' },
  { t: 'MSFT',  n: 'Microsoft' },
  { t: 'NFLX',  n: 'Netflix' },
  { t: 'NVDA',  n: 'NVIDIA' },
  { t: 'ORCL',  n: 'Oracle' },
  { t: 'PANW',  n: 'Palo Alto' },
  { t: 'PLTR',  n: 'Palantir' },
  { t: 'PYPL',  n: 'PayPal' },
  { t: 'QCOM',  n: 'Qualcomm' },
  { t: 'SNOW',  n: 'Snowflake' },
  { t: 'TSLA',  n: 'Tesla' },
  { t: 'UBER',  n: 'Uber' },
]

const STACK = [
  { f: 'deepseek.png',   n: 'DeepSeek V3' },
  { f: 'cerebras.png',   n: 'Cerebras' },
  { f: 'openai.png',     n: 'OpenAI' },
  { f: 'fastapi.svg',    n: 'FastAPI' },
  { f: 'react.svg',      n: 'React' },
  { f: 'typescript.svg', n: 'TypeScript' },
  { f: 'tailwind.svg',   n: 'Tailwind' },
  { f: 'vite.svg',       n: 'Vite' },
  { f: 'postgresql.png', n: 'PostgreSQL' },
  { f: 'supabase.png',   n: 'Supabase' },
  { f: 'tavily.png',     n: 'Tavily' },
  { f: 'clerk.png',      n: 'Clerk' },
  { f: 'langsmith.svg',  n: 'LangSmith' },
  { f: 'railway.png',    n: 'Railway' },
]

function CompanyTicker() {
  const doubled  = [...COMPANIES, ...COMPANIES]
  const trackRef = useInfiniteTicker(0.6)
  return (
    <motion.section
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: false, margin: '-80px' }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      className="bg-[#f3f4f6] py-14"
    >
      <div className="max-w-6xl mx-auto px-6 mb-10">
        <p className="text-xs font-mono uppercase tracking-[0.3em] text-neutral-400 mb-2">01 — Coverage</p>
        <h2 className="text-4xl md:text-5xl font-extrabold text-black tracking-tight">Coverage Universe</h2>
        <p className="text-base text-neutral-500 mt-2 max-w-xl">
          28 large-cap technology companies. Over 40,000+ SEC 10-K filings and quarterly earnings transcripts indexed from FY2023 to FY2026.
        </p>
      </div>
      <div className="relative overflow-hidden cursor-grab select-none">
        <div ref={trackRef} className="flex gap-14 items-end" style={{ width: 'max-content' }}>
          {doubled.map(({ t, n }, i) => (
            <div key={`${t}-${i}`} className="shrink-0 flex flex-col items-center gap-3 w-32">
              <img src={`/logos/${t}.svg`} alt={n} className="h-14 w-auto" style={{ filter: 'grayscale(100%)' }} />
              <span className="text-sm font-semibold text-black tracking-tight">{n}</span>
              <span className="text-[11px] text-neutral-400 font-mono">{t}</span>
            </div>
          ))}
        </div>
        <div className="pointer-events-none absolute left-0 top-0 bottom-0 w-24 bg-gradient-to-r from-[#f3f4f6] to-transparent" />
        <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-24 bg-gradient-to-l from-[#f3f4f6] to-transparent" />
      </div>
    </motion.section>
  )
}

function StackTicker() {
  const doubled  = [...STACK, ...STACK]
  const trackRef = useInfiniteTicker(0.9)
  return (
    <motion.section
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: false, margin: '-80px' }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      className="bg-[#f3f4f6] py-14"
    >
      <div className="max-w-6xl mx-auto px-6 mb-10">
        <p className="text-xs font-mono uppercase tracking-[0.3em] text-neutral-400 mb-2">03 — Stack</p>
        <h2 className="text-4xl md:text-5xl font-extrabold text-black tracking-tight">Built With Modern AI Stack</h2>
        <p className="text-base text-neutral-500 mt-2 max-w-xl">
          FastAPI + LangGraph backend, React + TypeScript frontend, PostgreSQL + pgvector, with DeepSeek, Cerebras, and OpenAI powering an agentic RAG pipeline.
        </p>
      </div>
      <div className="relative overflow-hidden cursor-grab select-none">
        <div ref={trackRef} className="flex gap-12 items-end" style={{ width: 'max-content' }}>
          {doubled.map(({ f, n }, i) => (
            <div key={`${f}-${i}`} className="shrink-0 flex flex-col items-center gap-3 w-28">
              <div className="h-14 w-14 bg-white rounded-xl border border-black/8 shadow-sm flex items-center justify-center p-2">
                <img src={`/stack_logos/${f}`} alt={n} className="max-h-10 max-w-[36px] w-auto object-contain" />
              </div>
              <span className="text-xs font-semibold text-neutral-700 tracking-tight">{n}</span>
            </div>
          ))}
        </div>
        <div className="pointer-events-none absolute left-0 top-0 bottom-0 w-24 bg-gradient-to-r from-neutral-50 to-transparent" />
        <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-24 bg-gradient-to-l from-neutral-50 to-transparent" />
      </div>
    </motion.section>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Features — compact card grid, alternating L/R pop-in
// ──────────────────────────────────────────────────────────────────────────

const FEATURES = [
  {
    icon: GitBranch,
    title: 'A 7-node reasoning graph',
    desc: 'Plan, search, generate, evaluate, rewrite, finalize. Every query travels a deterministic LangGraph pipeline that self-corrects when faithfulness scores fall below 0.65 — capped at two retries.',
    metric: '7 nodes',
  },
  {
    icon: Search,
    title: 'Hybrid retrieval, rerank-validated',
    desc: 'pgvector cosine search fused with BM25 Okapi via Reciprocal Rank Fusion, then reranked with a cross-encoder. Dual corpus: SEC 10-K filings and earnings transcripts.',
    metric: '42,000+ passages',
  },
  {
    icon: ShieldCheck,
    title: 'Faithfulness over fluency',
    desc: 'Every answer is groundedness-evaluated before delivery. Heuristic eval runs first; LLM-as-judge is invoked only on borderline scores. Confidence is surfaced inline.',
    metric: 'Heuristic + LLM judge',
  },
  {
    icon: Zap,
    title: 'Three providers, one API',
    desc: 'DeepSeek V3 primary for cost-efficient reasoning. Cerebras Qwen-3-235B for sub-second streaming. OpenAI GPT-4.1-mini as failsafe. Provider failover is automatic and transparent.',
    metric: 'Auto failover',
  },
  {
    icon: Globe,
    title: 'Optional live web augmentation',
    desc: 'Toggle web search to extend retrieval beyond the static corpus. Tavily fetches real-time news, press releases, and analyst commentary — cited alongside filing passages.',
    metric: 'Tavily',
  },
  {
    icon: RefreshCw,
    title: 'Semantic cache, near-zero latency',
    desc: 'Repeated or semantically equivalent queries are served from a pgvector cache at cosine ≥ 0.92. No round-trip, no token spend — just instant answers from prior runs.',
    metric: 'cosine ≥ 0.92',
  },
]

function FeatureCard({ feature, index }: { feature: typeof FEATURES[0]; index: number }) {
  const Icon    = feature.icon
  const fromLeft = index % 2 === 0
  return (
    <motion.div
      initial={{ opacity: 0, x: fromLeft ? -120 : 120 }}
      whileInView={{ opacity: 1, x: 0 }}
      viewport={{ once: false, margin: '-10px' }}
      transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
      className="border border-black/10 rounded-2xl p-6 bg-white hover:border-black/25 hover:shadow-sm transition-all group"
    >
      <div className="flex items-start gap-4">
        <div className="shrink-0 w-10 h-10 bg-black rounded-xl flex items-center justify-center group-hover:scale-105 transition-transform duration-300">
          <Icon className="w-5 h-5 text-white" strokeWidth={1.5} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[10px] font-mono text-neutral-400">0{index + 1}</span>
            <span className="text-[10px] font-mono bg-black/5 text-black px-2 py-0.5 rounded-full">{feature.metric}</span>
          </div>
          <h3 className="text-base font-bold text-black mb-2 leading-snug">{feature.title}</h3>
          <p className="text-sm text-neutral-600 leading-relaxed">{feature.desc}</p>
        </div>
      </div>
    </motion.div>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// GitHub icon (filled)
// ──────────────────────────────────────────────────────────────────────────

function GithubIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12Z" />
    </svg>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Page
// ──────────────────────────────────────────────────────────────────────────

export default function LandingPage() {
  const navigate = useNavigate()
  const { isSignedIn, signOut, user } = useAuthStatus()
  const [showAbout, setShowAbout]     = useState(false)
  const [showAuth,  setShowAuth]      = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [showScrollTop, setShowScrollTop] = useState(false)
  const profileRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onScroll = () => setShowScrollTop(window.scrollY > 400)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) setProfileOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const u: any = user
  const fullName    = `${u?.firstName ?? ''} ${u?.lastName ?? ''}`.trim() || u?.fullName || 'Account'
  const userInitial = (u?.firstName?.[0] || u?.emailAddresses?.[0]?.emailAddress?.[0] || 'U').toUpperCase()

  return (
    // No overflow-x-hidden on root — it breaks sticky positioning in Chrome
    <div className="min-h-screen bg-white text-black flex flex-col">
      <AboutModal isOpen={showAbout} onClose={() => setShowAbout(false)} />
      <AuthModal  isOpen={showAuth}  onClose={() => setShowAuth(false)} />

      {/* ── Nav — sticky, always visible ─────────────────────────── */}
      <nav className="sticky top-0 z-30 flex items-center justify-between px-6 md:px-10 py-4 bg-white/90 backdrop-blur border-b border-black/10">
        <button
          onClick={() => { window.location.href = '/' }}
          className="flex items-center gap-2.5 hover:opacity-80 transition-opacity"
        >
          <div className="w-12 h-12 bg-black rounded-xl flex items-center justify-center text-white text-xl font-black">α</div>
          <span className="text-2xl font-bold tracking-tight">AlphaLens</span>
        </button>

        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setShowAbout(true)}
            className="hidden sm:flex items-center gap-1.5 text-sm text-neutral-600 hover:text-black transition-colors px-2.5 py-1.5"
          >
            <Info className="w-4 h-4" />
            About
          </button>

          <a
            href="https://github.com/swapnil18800/alphalens"
            target="_blank" rel="noreferrer"
            className="flex items-center text-neutral-700 hover:text-black transition-colors p-2"
            title="GitHub"
          >
            <GithubIcon className="w-4 h-4" />
          </a>

          {AUTH_AVAILABLE && !isSignedIn && (
            <button
              onClick={() => setShowAuth(true)}
              className="flex items-center gap-1.5 text-sm text-black px-3 py-1.5 rounded-lg hover:bg-black/5 transition-colors font-medium"
            >
              <LogIn className="w-3.5 h-3.5" />
              Sign in
            </button>
          )}

          {AUTH_AVAILABLE && isSignedIn && (
            <div className="relative" ref={profileRef}>
              <button
                onClick={() => setProfileOpen(v => !v)}
                className="w-8 h-8 rounded-full overflow-hidden bg-black flex items-center justify-center text-white text-xs font-bold ring-1 ring-black/10 hover:opacity-80 transition-opacity"
                title={fullName}
              >
                {u?.imageUrl
                  ? <img src={u.imageUrl} className="w-full h-full object-cover" alt={fullName} referrerPolicy="no-referrer" />
                  : <span>{userInitial}</span>}
              </button>
              {profileOpen && (
                <div className="absolute right-0 top-10 bg-white border border-black/10 rounded-xl shadow-xl p-1.5 min-w-44 z-40">
                  <div className="px-3 py-2 border-b border-black/5 mb-1">
                    <p className="text-sm font-semibold text-black truncate">{fullName}</p>
                  </div>
                  <button
                    onClick={() => { setProfileOpen(false); signOut() }}
                    className="w-full text-left px-3 py-2 text-sm text-neutral-700 hover:bg-black hover:text-white rounded-lg transition-colors"
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>
          )}

          <button
            onClick={() => navigate('/chat')}
            className="flex items-center gap-1.5 bg-black hover:bg-neutral-800 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors ml-1"
          >
            Open App <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </nav>

      {/* ── Hero ─────────────────────────────────────────────────────── */}
      <section className="relative flex flex-col items-center text-center px-6 pt-32 pb-32 overflow-hidden">
        <GeometricBackground />
        <motion.div
          className="relative flex flex-col items-center gap-8 max-w-4xl"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        >
          <h1 className="text-6xl md:text-7xl lg:text-[5.5rem] font-extrabold leading-[1.02] tracking-tight">
            Equity analyst workflows,
            <br />
            <span className="italic font-medium">reimagined.</span>
          </h1>
          <p className="text-neutral-600 text-lg md:text-xl max-w-2xl leading-relaxed">
            Stop digging through filings manually. AlphaLens does the heavy lifting — retrieve, reason, and cite across 40,000+ SEC filings and earnings transcripts in seconds.
          </p>
          <div className="flex flex-wrap justify-center gap-3 mt-2">
            <button
              onClick={() => navigate('/chat')}
              className="flex items-center gap-2 bg-black hover:bg-neutral-800 text-white font-semibold px-7 py-3.5 rounded-xl transition-colors shadow-sm"
            >
              Start Researching <ArrowRight className="w-4 h-4" />
            </button>
            <a
              href="https://github.com/swapnil18800/alphalens"
              target="_blank" rel="noreferrer"
              className="flex items-center gap-2 bg-white border border-black/15 hover:border-black hover:bg-black hover:text-white text-black px-7 py-3.5 rounded-xl transition-colors font-semibold"
            >
              <GithubIcon className="w-4 h-4" /> View Source
            </a>
          </div>
        </motion.div>
      </section>

      <SectionTransition from="white" to="#f3f4f6" />

      {/* ── Coverage Universe ────────────────────────────────────────── */}
      <CompanyTicker />

      <SectionTransition from="#f3f4f6" to="#f9fafb" />

      {/* ── Features — compact card grid ─────────────────────────────── */}
      <motion.section
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: false, margin: '-80px' }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="w-full bg-[#f9fafb] py-20"
      >
      <div className="px-6 max-w-6xl mx-auto">
        <div className="mb-12 max-w-2xl">
          <p className="text-xs font-mono uppercase tracking-[0.3em] text-neutral-400 mb-3">02 — Architecture</p>
          <h2 className="text-4xl md:text-5xl font-extrabold tracking-tight mb-4 leading-tight">
            Six engineering choices,<br />one honest answer.
          </h2>
          <p className="text-neutral-600 text-base leading-relaxed">
            What separates AlphaLens from a generic LLM chatbot — every layer optimised for retrieval grounding,
            faithful generation, and transparent reasoning.
          </p>
        </div>
        <div className="grid md:grid-cols-2 gap-4">
          {FEATURES.map((f, i) => <FeatureCard key={f.title} feature={f} index={i} />)}
        </div>
      </div>
      </motion.section>

      <SectionTransition from="#f9fafb" to="#f3f4f6" />

      {/* ── Built With ────────────────────────────────────────────────── */}
      <StackTicker />

      <SectionTransition from="#f3f4f6" to="white" />

      {/* ── CTA ──────────────────────────────────────────────────────── */}
      <motion.section
        initial={{ opacity: 0, y: 16 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: false }}
        className="px-6 py-28 bg-white"
      >
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-4xl md:text-5xl font-extrabold mb-4 tracking-tight">Ask your first question.</h2>
          <p className="text-neutral-600 text-base mb-9 max-w-md mx-auto leading-relaxed">
            No setup. No credit card. Sign in to save research history across devices, or jump straight in as a guest.
          </p>
          <div className="flex flex-wrap gap-3 justify-center">
            <button
              onClick={() => navigate('/chat')}
              className="inline-flex items-center gap-2 bg-black hover:bg-neutral-800 text-white font-semibold px-8 py-3.5 rounded-xl transition-colors"
            >
              Open AlphaLens <ArrowRight className="w-4 h-4" />
            </button>
            {AUTH_AVAILABLE && !isSignedIn && (
              <button
                onClick={() => setShowAuth(true)}
                className="inline-flex items-center gap-2 bg-white border border-black hover:bg-black hover:text-white text-black font-semibold px-8 py-3.5 rounded-xl transition-colors"
              >
                Sign In
              </button>
            )}
          </div>
        </div>
      </motion.section>

      {/* ── Scroll-to-top button ─────────────────────────────────────── */}
      <AnimatePresence>
        {showScrollTop && (
          <motion.button
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            transition={{ duration: 0.2 }}
            onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
            className="fixed bottom-8 right-8 z-40 w-11 h-11 bg-black text-white rounded-full shadow-lg hover:bg-neutral-800 hover:shadow-xl transition-all flex items-center justify-center"
            title="Back to top"
          >
            <ArrowUp className="w-4 h-4" />
          </motion.button>
        )}
      </AnimatePresence>

      {/* ── Footer ───────────────────────────────────────────────────── */}
      <footer className="border-t border-black/10 bg-white px-6 md:px-10 py-8">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-neutral-500">
          <div className="flex items-center gap-3">
            <div className="w-5 h-5 bg-black rounded flex items-center justify-center text-white font-black text-[10px]">α</div>
            <span>© 2025 AlphaLens · Built by Swapnil Padhi · MIT License</span>
          </div>
          <div className="flex flex-col sm:flex-row items-center gap-3 sm:gap-4 text-center">
            <span className="text-black font-medium">AI may make errors — verify before acting on financial data</span>
            <div className="flex items-center gap-3">
              <a href="https://github.com/swapnil18800/alphalens" target="_blank" rel="noreferrer" className="hover:text-black transition-colors">GitHub</a>
              <button onClick={() => setShowAbout(true)} className="hover:text-black transition-colors">About</button>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
