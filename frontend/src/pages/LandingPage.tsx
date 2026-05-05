import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ArrowRight, Github, Search, Zap, Globe, ShieldCheck,
  GitBranch, RefreshCw, ChevronRight, Info, LogIn, UserPlus,
} from 'lucide-react'
import AboutModal from '../components/AboutModal'
import AuthModal from '../components/AuthModal'
import { AUTH_AVAILABLE } from '../lib/config'
import { useAuthStatus } from '../hooks/useAuthStatus'

// ── Motion variants ───────────────────────────────────────────────────────

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: (i = 0) => ({
    opacity: 1, y: 0,
    transition: { duration: 0.55, delay: i * 0.1, ease: [0.22, 1, 0.36, 1] as const },
  }),
}

const stagger = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.08 } },
}

// ── Animated background ───────────────────────────────────────────────────

function AnimatedBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animId: number
    const resize = () => {
      const p = canvas.parentElement
      if (p) { canvas.width = p.offsetWidth; canvas.height = p.offsetHeight }
    }
    requestAnimationFrame(resize)
    const ro = new ResizeObserver(() => requestAnimationFrame(resize))
    if (canvas.parentElement) ro.observe(canvas.parentElement)
    window.addEventListener('resize', resize)

    const N = 90
    const particles = Array.from({ length: N }, () => ({
      x: Math.random() * (canvas.width || window.innerWidth),
      y: Math.random() * (canvas.height || 600),
      vx: (Math.random() - 0.5) * 0.35,
      vy: (Math.random() - 0.5) * 0.35,
      r: Math.random() * 1.8 + 0.6,
    }))

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      for (let i = 0; i < N; i++) {
        for (let j = i + 1; j < N; j++) {
          const dx = particles[i].x - particles[j].x
          const dy = particles[i].y - particles[j].y
          const d = Math.sqrt(dx * dx + dy * dy)
          if (d < 140) {
            ctx.beginPath()
            ctx.moveTo(particles[i].x, particles[i].y)
            ctx.lineTo(particles[j].x, particles[j].y)
            ctx.strokeStyle = `rgba(99,102,241,${0.22 * (1 - d / 140)})`
            ctx.lineWidth = 0.7
            ctx.stroke()
          }
        }
      }
      for (const p of particles) {
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fillStyle = 'rgba(99,102,241,0.45)'
        ctx.fill()
        p.x += p.vx; p.y += p.vy
        if (p.x < 0 || p.x > canvas.width) p.vx *= -1
        if (p.y < 0 || p.y > canvas.height) p.vy *= -1
      }
      animId = requestAnimationFrame(draw)
    }
    draw()

    return () => { cancelAnimationFrame(animId); ro.disconnect(); window.removeEventListener('resize', resize) }
  }, [])

  return <canvas ref={canvasRef} className="absolute inset-0 w-full h-full pointer-events-none" style={{ opacity: 0.7 }} />
}

// ── Logo ticker ───────────────────────────────────────────────────────────

const TICKERS = ['AAPL','ADBE','AMD','AMZN','AVGO','CRM','CSCO','GOOGL','IBM','INTC','META','MSFT','NFLX','NVDA','ORCL','PANW','PLTR','PYPL','QCOM','SNOW','TSLA','UBER']

// Tech-stack pills — no external images needed
const TECH_STACK = [
  { name: 'DeepSeek V3',   color: '#4D6BFE' },
  { name: 'LangGraph',     color: '#1a7f37' },
  { name: 'FastAPI',       color: '#009688' },
  { name: 'pgvector',      color: '#7c5bdb' },
  { name: 'React 18',      color: '#61DAFB', dark: true },
  { name: 'PostgreSQL',    color: '#336791' },
  { name: 'Tailwind CSS',  color: '#06B6D4', dark: true },
  { name: 'Vite',          color: '#646cff' },
  { name: 'Cerebras',      color: '#e5523f' },
  { name: 'Tavily',        color: '#ff6b35' },
  { name: 'Clerk',         color: '#6c47ff' },
  { name: 'BM25',          color: '#475569' },
]

function LogoTicker() {
  // Double for seamless infinite loop
  const doubled = [...TICKERS, ...TICKERS]
  return (
    <div className="border-y border-slate-200 bg-white/70 overflow-hidden py-5">
      <p className="text-center text-[10px] font-mono text-slate-400 uppercase tracking-widest mb-4">
        Coverage universe
      </p>
      <div className="relative">
        <div className="flex ticker-track gap-8 items-center">
          {doubled.map((t, i) => (
            <img
              key={`${t}-${i}`}
              src={`/logos/${t}.svg`}
              alt={t}
              className="h-7 w-auto shrink-0"
              style={{ filter: 'grayscale(100%) opacity(0.45)' }}
            />
          ))}
        </div>
      </div>
      {/* Fade edges */}
      <div className="pointer-events-none absolute left-0 top-0 bottom-0 w-20 bg-gradient-to-r from-white to-transparent" />
      <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-20 bg-gradient-to-l from-white to-transparent" />
    </div>
  )
}

function TechTicker() {
  const doubled = [...TECH_STACK, ...TECH_STACK]
  return (
    <div className="overflow-hidden py-4 bg-slate-50/80 border-b border-slate-200">
      <p className="text-center text-[10px] font-mono text-slate-400 uppercase tracking-widest mb-3">
        Built with
      </p>
      <div className="flex ticker-track-fast gap-3 items-center">
        {doubled.map(({ name, color, dark }, i) => (
          <span
            key={`${name}-${i}`}
            className="shrink-0 px-3 py-1 rounded-full text-[11px] font-semibold tracking-wide"
            style={{
              backgroundColor: color + '18',
              color: dark ? color : color,
              border: `1px solid ${color}30`,
            }}
          >
            {name}
          </span>
        ))}
      </div>
    </div>
  )
}

// ── Static data ───────────────────────────────────────────────────────────

const FEATURES = [
  {
    icon: Search,
    title: 'Hybrid RAG Retrieval',
    desc: 'pgvector cosine search fused with BM25 Okapi via Reciprocal Rank Fusion, then reranked by a cross-encoder. Dual corpus: SEC 10-K filings + earnings transcripts.',
  },
  {
    icon: GitBranch,
    title: 'LangGraph Agent Pipeline',
    desc: '5-node deterministic graph: analyze → search → generate → evaluate → retry. Self-corrects when faithfulness score drops below threshold (max 2 retries).',
  },
  {
    icon: Globe,
    title: 'Live Web Search Augmentation',
    desc: 'Optionally extend retrieval beyond the static 42K-passage corpus with Tavily real-time news, press releases, and analyst commentary.',
  },
  {
    icon: ShieldCheck,
    title: 'Faithfulness Scoring',
    desc: 'Heuristic eval runs first; LLM-as-judge only for borderline scores (0.50–0.75) on the first iteration. Confidence badge surfaced inline on every answer.',
  },
  {
    icon: Zap,
    title: 'Multi-Provider LLM Routing',
    desc: 'DeepSeek V3 primary for cost-efficient inference, Cerebras Qwen-3-235B for speed, OpenAI GPT-4.1-mini as failsafe — automatic failover with zero config.',
  },
  {
    icon: RefreshCw,
    title: 'Semantic Response Cache',
    desc: 'Cosine similarity ≥ 0.92 threshold on query embeddings. Near-zero latency on repeated or semantically equivalent questions; cache stored in pgvector.',
  },
]

const PIPELINE = [
  { label: 'Analyze',  desc: 'Intent · tickers · sub-questions' },
  { label: 'Search',   desc: 'pgvector + BM25 → RRF → cross-encoder' },
  { label: 'Generate', desc: 'DeepSeek V3 / Cerebras streaming' },
  { label: 'Evaluate', desc: 'Heuristic + LLM-as-judge faithfulness' },
  { label: 'Deliver',  desc: 'WebSocket tokens + source citations' },
]

const STATS = [
  { value: '27',      label: 'Companies covered' },
  { value: '42K+',    label: 'Indexed passages' },
  { value: 'FY23–26', label: 'Filing range' },
  { value: '5-node',  label: 'Agent graph' },
]

// ── GitHub filled icon (SVG path) ─────────────────────────────────────────

function GithubIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12Z" />
    </svg>
  )
}

// ── Component ─────────────────────────────────────────────────────────────

export default function LandingPage() {
  const navigate = useNavigate()
  const { isSignedIn, signOut } = useAuthStatus()
  const [showAbout, setShowAbout] = useState(false)
  const [showAuth, setShowAuth] = useState(false)
  const [authTab, setAuthTab] = useState<'sign-in' | 'sign-up'>('sign-in')
  const [profileOpen, setProfileOpen] = useState(false)
  const profileRef = useRef<HTMLDivElement>(null)

  // Close profile dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setProfileOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const openSignIn = () => { setAuthTab('sign-in'); setShowAuth(true) }
  const openSignUp = () => { setAuthTab('sign-up'); setShowAuth(true) }

  return (
    <div className="min-h-screen bg-[#faf9f7] text-[#0a1628] flex flex-col overflow-x-hidden">
      <AboutModal isOpen={showAbout} onClose={() => setShowAbout(false)} />
      <AuthModal isOpen={showAuth} onClose={() => setShowAuth(false)} defaultTab={authTab} />

      {/* ── Nav ──────────────────────────────────────────────────────── */}
      <nav className="sticky top-0 z-30 flex items-center justify-between px-8 py-4 bg-white/85 backdrop-blur border-b border-slate-200/80">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 bg-[#0a1628] rounded-lg flex items-center justify-center text-white text-sm font-black">α</div>
          <span className="text-base font-bold tracking-tight">AlphaLens</span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowAbout(true)}
            className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-[#0a1628] transition-colors px-2 py-1.5"
            title="About"
          >
            <Info className="w-4 h-4" />
            <span className="hidden sm:inline">About</span>
          </button>

          <a
            href="https://github.com/swapnil18800/alphalens"
            target="_blank" rel="noreferrer"
            className="flex items-center text-slate-500 hover:text-[#0a1628] transition-colors px-2 py-1.5"
            title="GitHub"
          >
            <GithubIcon className="w-4 h-4" />
          </a>

          {/* Auth section */}
          {AUTH_AVAILABLE && !isSignedIn && (
            <>
              <button
                onClick={openSignIn}
                className="flex items-center gap-1.5 text-sm text-slate-600 hover:text-[#0a1628] px-3 py-1.5 rounded-lg hover:bg-slate-100 transition-colors"
              >
                <LogIn className="w-3.5 h-3.5" />
                Sign In
              </button>
              <button
                onClick={openSignUp}
                className="flex items-center gap-1.5 text-sm bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1.5 rounded-lg transition-colors"
              >
                <UserPlus className="w-3.5 h-3.5" />
                Sign Up
              </button>
            </>
          )}

          {AUTH_AVAILABLE && isSignedIn && (
            <div className="relative" ref={profileRef}>
              <button
                onClick={() => setProfileOpen(v => !v)}
                className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center text-white text-sm font-bold hover:bg-indigo-700 transition-colors"
                title="Account"
              >
                α
              </button>
              {profileOpen && (
                <div className="absolute right-0 top-10 bg-white border border-slate-200 rounded-xl shadow-lg p-1.5 min-w-36 z-40">
                  <button
                    onClick={() => { setProfileOpen(false); signOut() }}
                    className="w-full text-left px-3 py-2 text-sm text-slate-600 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>
          )}

          <button
            onClick={() => navigate('/chat')}
            className="flex items-center gap-1.5 bg-[#0a1628] hover:bg-slate-800 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors ml-1"
          >
            Open App <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </nav>

      {/* ── Hero ─────────────────────────────────────────────────────── */}
      <section className="relative flex flex-col items-center text-center px-6 pt-28 pb-24 overflow-hidden">
        <AnimatedBackground />
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute -top-40 left-1/4 w-[700px] h-[700px] rounded-full bg-indigo-100 opacity-30 blur-3xl" />
          <div className="absolute top-20 right-0 w-[500px] h-[500px] rounded-full bg-blue-100 opacity-20 blur-3xl" />
          <div className="absolute bottom-0 left-0 w-[400px] h-[400px] rounded-full bg-violet-50 opacity-25 blur-3xl" />
        </div>

        <motion.div
          className="relative flex flex-col items-center gap-6 max-w-3xl"
          variants={stagger} initial="hidden" animate="visible"
        >
          <motion.div variants={fadeUp} custom={0} className="inline-flex items-center gap-2 bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-medium px-3 py-1.5 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse inline-block" />
            Powered by DeepSeek V3 + LangGraph RAG pipeline
          </motion.div>

          <motion.h1
            variants={fadeUp} custom={1}
            className="text-5xl md:text-[3.8rem] font-extrabold leading-[1.08] tracking-tight"
          >
            Agentic AI research
            <br className="hidden sm:block" />
            <span className="bg-gradient-to-r from-indigo-600 via-blue-600 to-indigo-500 bg-clip-text text-transparent">
              {' '}for equity analysts
            </span>
          </motion.h1>

          <motion.p
            variants={fadeUp} custom={2}
            className="text-slate-600 text-base sm:text-lg max-w-xl leading-relaxed"
          >
            Ask deep questions about SEC 10-K filings and earnings calls.
            AlphaLens reasons over your query, retrieves from 42,000+ indexed passages
            across 27 companies, and returns a grounded, cited answer in seconds.
          </motion.p>

          <motion.div variants={fadeUp} custom={3} className="flex flex-wrap justify-center gap-3">
            <button
              onClick={() => navigate('/chat')}
              className="flex items-center gap-2 bg-[#0a1628] hover:bg-slate-800 text-white font-semibold px-6 py-3 rounded-xl transition-colors shadow-md"
            >
              Start Researching <ArrowRight className="w-4 h-4" />
            </button>
            {AUTH_AVAILABLE && !isSignedIn && (
              <button
                onClick={openSignUp}
                className="flex items-center gap-2 bg-white border border-slate-300 hover:border-indigo-400 hover:text-indigo-700 text-slate-600 px-6 py-3 rounded-xl transition-colors"
              >
                <UserPlus className="w-4 h-4" /> Create Account
              </button>
            )}
            {(!AUTH_AVAILABLE || isSignedIn) && (
              <a
                href="https://github.com/swapnil18800/alphalens"
                target="_blank" rel="noreferrer"
                className="flex items-center gap-2 bg-white border border-slate-300 hover:border-slate-400 text-slate-600 hover:text-[#0a1628] px-6 py-3 rounded-xl transition-colors"
              >
                <GithubIcon className="w-4 h-4" /> View Source
              </a>
            )}
          </motion.div>

          <motion.p variants={fadeUp} custom={4} className="text-xs text-slate-400 font-mono mt-1">
            No sign-up required · AAPL · META · NVDA · MSFT · GOOGL + 22 more
          </motion.p>
        </motion.div>
      </section>

      {/* ── Company logo ticker ───────────────────────────────────────── */}
      <div className="relative">
        <LogoTicker />
      </div>

      {/* ── Tech stack ticker ─────────────────────────────────────────── */}
      <TechTicker />

      {/* ── Stats ────────────────────────────────────────────────────── */}
      <section className="border-b border-slate-200 bg-white">
        <div className="max-w-4xl mx-auto px-6 py-7 grid grid-cols-2 sm:grid-cols-4 gap-6">
          {STATS.map(({ value, label }, i) => (
            <motion.div
              key={label}
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.07 }}
              className="text-center"
            >
              <p className="text-2xl font-bold text-[#0a1628]">{value}</p>
              <p className="text-xs text-slate-400 mt-0.5">{label}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── Pipeline ─────────────────────────────────────────────────── */}
      <section className="px-6 py-16">
        <div className="max-w-5xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center mb-10"
          >
            <h2 className="text-2xl font-bold text-[#0a1628] mb-2">How a query runs</h2>
            <p className="text-sm text-slate-400">Five deterministic steps, every time — self-correcting on low confidence</p>
          </motion.div>

          <div className="flex flex-col sm:flex-row">
            {PIPELINE.map(({ label, desc }, i) => (
              <motion.div
                key={label}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.09 }}
                className="relative flex-1"
              >
                <div className="bg-white border border-slate-200 p-4 h-full sm:first:rounded-l-xl sm:last:rounded-r-xl rounded-xl sm:rounded-none sm:border-r-0 sm:last:border-r mb-px sm:mb-0 hover:bg-slate-50 transition-colors">
                  <span className="block text-[9px] font-mono text-slate-300 mb-1 tracking-widest">0{i + 1}</span>
                  <span className="block font-semibold text-sm text-[#0a1628] mb-1">{label}</span>
                  <span className="block text-xs text-slate-400 leading-relaxed">{desc}</span>
                </div>
                {i < PIPELINE.length - 1 && (
                  <div className="hidden sm:flex absolute right-0 top-1/2 -translate-y-1/2 translate-x-[1px] z-10 bg-[#faf9f7] px-0.5">
                    <ChevronRight className="w-3 h-3 text-slate-300" />
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Features ─────────────────────────────────────────────────── */}
      <section className="px-6 pt-4 pb-20 bg-white border-t border-slate-200">
        <div className="max-w-5xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center mb-10 pt-12"
          >
            <h2 className="text-2xl font-bold text-[#0a1628] mb-2">What's under the hood</h2>
            <p className="text-sm text-slate-400">Production-grade RAG + multi-agent reasoning, built for financial research at scale</p>
          </motion.div>

          <motion.div
            variants={stagger}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-60px' }}
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
          >
            {FEATURES.map(({ icon: Icon, title, desc }) => (
              <motion.div
                key={title}
                variants={fadeUp}
                className="bg-[#faf9f7] border border-slate-200 rounded-xl p-5 hover:border-indigo-200 hover:shadow-sm transition-all"
              >
                <div className="w-8 h-8 bg-indigo-50 rounded-lg flex items-center justify-center mb-3">
                  <Icon className="w-4 h-4 text-indigo-600" strokeWidth={1.75} />
                </div>
                <h3 className="font-semibold text-sm text-[#0a1628] mb-1">{title}</h3>
                <p className="text-slate-500 text-sm leading-relaxed">{desc}</p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── CTA ──────────────────────────────────────────────────────── */}
      <section className="px-6 py-20 bg-[#0a1628] text-white relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[200px] rounded-full bg-indigo-600 opacity-10 blur-3xl" />
        </div>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="max-w-2xl mx-auto text-center relative"
        >
          <h2 className="text-2xl font-bold mb-3">Ready to research?</h2>
          <p className="text-slate-400 text-sm mb-7 max-w-md mx-auto leading-relaxed">
            Instant access — no setup required. Sign up to save sessions and get persistent research history across devices.
          </p>
          <div className="flex flex-wrap gap-3 justify-center">
            <button
              onClick={() => navigate('/chat')}
              className="inline-flex items-center gap-2 bg-white text-[#0a1628] hover:bg-slate-100 font-semibold px-8 py-3 rounded-xl transition-colors shadow-sm"
            >
              Open AlphaLens <ArrowRight className="w-4 h-4" />
            </button>
            {AUTH_AVAILABLE && !isSignedIn && (
              <button
                onClick={openSignUp}
                className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-8 py-3 rounded-xl transition-colors"
              >
                <UserPlus className="w-4 h-4" /> Create Free Account
              </button>
            )}
          </div>
        </motion.div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────── */}
      <footer className="border-t border-slate-200 bg-white px-8 py-6">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-400">
          <div className="flex items-center gap-3">
            <div className="w-5 h-5 bg-[#0a1628] rounded flex items-center justify-center text-white font-black text-[10px]">α</div>
            <span>© 2025 AlphaLens · Built by Swapnil Padhi · MIT License</span>
          </div>
          <div className="flex flex-col sm:flex-row items-center gap-2 sm:gap-4 text-center">
            <span className="text-amber-600 font-medium">AI responses may contain errors — verify before acting on financial data</span>
            <div className="flex items-center gap-3">
              <a href="https://github.com/swapnil18800/alphalens" target="_blank" rel="noreferrer" className="hover:text-[#0a1628] transition-colors">GitHub</a>
              <button onClick={() => setShowAbout(true)} className="hover:text-[#0a1628] transition-colors">About</button>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
