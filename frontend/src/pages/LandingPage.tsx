import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ArrowRight, Github, Search, Zap, Globe, ShieldCheck,
  GitBranch, RefreshCw, ChevronRight, Info,
} from 'lucide-react'
import AboutModal from '../components/AboutModal'

// ── Framer Motion variants ────────────────────────────────────────────────

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

// ── Animated particle network background ─────────────────────────────────

function AnimatedBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animId: number

    const resize = () => {
      const parent = canvas.parentElement
      if (!parent) return
      canvas.width  = parent.offsetWidth
      canvas.height = parent.offsetHeight
    }

    // Initial resize deferred so layout is complete
    requestAnimationFrame(resize)

    // ResizeObserver keeps canvas in sync as hero section grows/shrinks
    const ro = new ResizeObserver(() => requestAnimationFrame(resize))
    if (canvas.parentElement) ro.observe(canvas.parentElement)
    window.addEventListener('resize', resize)

    // More particles for full-hero coverage
    const N = 90
    const particles = Array.from({ length: N }, () => ({
      x:  Math.random() * (canvas.width  || window.innerWidth),
      y:  Math.random() * (canvas.height || 600),
      vx: (Math.random() - 0.5) * 0.35,
      vy: (Math.random() - 0.5) * 0.35,
      r:  Math.random() * 1.8 + 0.6,
    }))

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)

      // Connection lines
      for (let i = 0; i < N; i++) {
        for (let j = i + 1; j < N; j++) {
          const dx = particles[i].x - particles[j].x
          const dy = particles[i].y - particles[j].y
          const d  = Math.sqrt(dx * dx + dy * dy)
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

      // Dots
      for (const p of particles) {
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fillStyle = 'rgba(99,102,241,0.45)'
        ctx.fill()

        p.x += p.vx
        p.y += p.vy
        if (p.x < 0 || p.x > canvas.width)  p.vx *= -1
        if (p.y < 0 || p.y > canvas.height) p.vy *= -1
      }

      animId = requestAnimationFrame(draw)
    }
    draw()

    return () => {
      cancelAnimationFrame(animId)
      ro.disconnect()
      window.removeEventListener('resize', resize)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full pointer-events-none"
      style={{ opacity: 0.7 }}
    />
  )
}

// ── Data ──────────────────────────────────────────────────────────────────

const FEATURES = [
  {
    icon: Search,
    title: 'Hybrid RAG Retrieval',
    desc: 'pgvector cosine search fused with BM25 via RRF, then re-ranked by a cross-encoder for high-precision recall',
  },
  {
    icon: GitBranch,
    title: 'LangGraph Agent Pipeline',
    desc: 'Multi-node reasoning graph: analyze → search → generate → evaluate → retry — expands scope when confidence falls short',
  },
  {
    icon: Globe,
    title: 'Live Web Search',
    desc: 'Optionally augment responses with Tavily real-time news and analyst commentary beyond the static filing corpus',
  },
  {
    icon: ShieldCheck,
    title: 'Faithfulness Scoring',
    desc: 'Every response is groundedness-evaluated before delivery — confidence badge surfaced inline on every answer',
  },
  {
    icon: Zap,
    title: 'Cerebras + OpenAI Routing',
    desc: 'Qwen-3-235B on Cerebras for near-instant streaming inference — automatic fallover to GPT-4o-mini on rate limits',
  },
  {
    icon: RefreshCw,
    title: 'Semantic Response Cache',
    desc: 'Semantically similar queries are served from a pgvector cache — near-zero latency on repeated questions',
  },
]

const PIPELINE = [
  { label: 'Analyze',  desc: 'Intent · tickers · sub-questions' },
  { label: 'Search',   desc: 'pgvector · BM25 · RRF · rerank' },
  { label: 'Generate', desc: 'Cerebras Qwen-3 streaming' },
  { label: 'Evaluate', desc: 'Faithfulness scoring' },
  { label: 'Deliver',  desc: 'WebSocket stream + citations' },
]

const STATS = [
  { value: '27',      label: 'Companies covered' },
  { value: '42K+',    label: 'Indexed passages' },
  { value: 'FY23–26', label: 'Filing range' },
  { value: '5-node',  label: 'Agent graph' },
]

// FAANG first, then others
const TICKER_LINE = 'AAPL · META · NFLX · GOOGL · MSFT · NVDA · TSLA · IBM · CSCO · SNOW + 17 more'

// ── Component ─────────────────────────────────────────────────────────────

export default function LandingPage() {
  const navigate = useNavigate()
  const [showAbout, setShowAbout] = useState(false)

  return (
    <div className="min-h-screen bg-[#faf9f7] text-[#0a1628] flex flex-col overflow-x-hidden">

      <AboutModal isOpen={showAbout} onClose={() => setShowAbout(false)} />

      {/* ── Nav ──────────────────────────────────────────────────────── */}
      <nav className="sticky top-0 z-30 flex items-center justify-between px-8 py-4 bg-white/80 backdrop-blur border-b border-slate-200/80">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 bg-[#0a1628] rounded-lg flex items-center justify-center text-white text-sm font-black">
            α
          </div>
          <span className="text-base font-bold tracking-tight">AlphaLens</span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowAbout(true)}
            className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-[#0a1628] transition-colors"
            title="About AlphaLens"
          >
            <Info className="w-4 h-4" />
            <span className="hidden sm:inline">About</span>
          </button>
          <a
            href="https://github.com/swapnil18800/alphalens"
            target="_blank" rel="noreferrer"
            className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-[#0a1628] transition-colors"
          >
            <Github className="w-4 h-4" />
            <span className="hidden sm:inline">GitHub</span>
          </a>
          <button
            onClick={() => navigate('/chat')}
            className="flex items-center gap-1.5 bg-[#0a1628] hover:bg-slate-800 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            Open App <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </nav>

      {/* ── Hero ─────────────────────────────────────────────────────── */}
      <section className="relative flex flex-col items-center text-center px-6 pt-28 pb-24 overflow-hidden">
        {/* Animated canvas — fills entire hero section via absolute inset-0 */}
        <AnimatedBackground />

        {/* Gradient blobs */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute -top-40 left-1/4 w-[700px] h-[700px] rounded-full bg-indigo-100 opacity-30 blur-3xl" />
          <div className="absolute top-20 right-0 w-[500px] h-[500px] rounded-full bg-blue-100 opacity-20 blur-3xl" />
          <div className="absolute bottom-0 left-0 w-[400px] h-[400px] rounded-full bg-violet-50 opacity-25 blur-3xl" />
        </div>

        <motion.div
          className="relative flex flex-col items-center gap-6 max-w-3xl"
          variants={stagger} initial="hidden" animate="visible"
        >
          <motion.h1
            variants={fadeUp} custom={0}
            className="text-5xl md:text-[3.8rem] font-extrabold leading-[1.08] tracking-tight"
          >
            Agentic AI research
            <br className="hidden sm:block" />
            <span className="bg-gradient-to-r from-indigo-600 via-blue-600 to-indigo-500 bg-clip-text text-transparent">
              {' '}for equity analysts
            </span>
          </motion.h1>

          <motion.p
            variants={fadeUp} custom={1}
            className="text-slate-600 text-base sm:text-lg max-w-xl leading-relaxed"
          >
            Ask deep questions about SEC 10-K filings and earnings calls —
            AlphaLens reasons over your query, searches 42,000+ indexed passages,
            and returns a grounded, cited answer in seconds
          </motion.p>

          <motion.div variants={fadeUp} custom={2} className="flex flex-wrap justify-center gap-3">
            <button
              onClick={() => navigate('/chat')}
              className="flex items-center gap-2 bg-[#0a1628] hover:bg-slate-800 text-white font-semibold px-6 py-3 rounded-xl transition-colors shadow-md"
            >
              Start Researching <ArrowRight className="w-4 h-4" />
            </button>
            <a
              href="https://github.com/swapnil18800/alphalens"
              target="_blank" rel="noreferrer"
              className="flex items-center gap-2 bg-white border border-slate-300 hover:border-slate-400 text-slate-600 hover:text-[#0a1628] px-6 py-3 rounded-xl transition-colors"
            >
              <Github className="w-4 h-4" /> View Source
            </a>
          </motion.div>

          <motion.p
            variants={fadeUp} custom={3}
            className="text-xs text-slate-400 font-mono mt-1"
          >
            {TICKER_LINE}
          </motion.p>
        </motion.div>
      </section>

      {/* ── Stats ────────────────────────────────────────────────────── */}
      <section className="border-y border-slate-200 bg-white">
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
            <p className="text-sm text-slate-400">Five deterministic steps, every time</p>
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
                <div className="bg-white border border-slate-200 p-4 h-full
                  sm:first:rounded-l-xl sm:last:rounded-r-xl
                  rounded-xl sm:rounded-none
                  sm:border-r-0 sm:last:border-r
                  mb-px sm:mb-0
                  hover:bg-slate-50 transition-colors"
                >
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
            <p className="text-sm text-slate-400">Production-grade RAG + multi-agent reasoning pipeline</p>
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
                className="bg-[#faf9f7] border border-slate-200 rounded-xl p-5 hover:border-slate-300 hover:shadow-sm transition-all"
              >
                <div className="w-8 h-8 bg-slate-100 rounded-lg flex items-center justify-center mb-3">
                  <Icon className="w-4 h-4 text-slate-600" strokeWidth={1.75} />
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
            Ask anything about SEC filings, risk factors, revenue trends, or earnings calls —
            no sign-up required
          </p>
          <button
            onClick={() => navigate('/chat')}
            className="inline-flex items-center gap-2 bg-white text-[#0a1628] hover:bg-slate-100 font-semibold px-8 py-3 rounded-xl transition-colors shadow-sm"
          >
            Open AlphaLens <ArrowRight className="w-4 h-4" />
          </button>
        </motion.div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────── */}
      <footer className="border-t border-slate-200 bg-white px-8 py-6">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-400">
          <div className="flex items-center gap-3">
            <div className="w-5 h-5 bg-[#0a1628] rounded flex items-center justify-center text-white font-black text-[10px]">α</div>
            <span>© 2024 AlphaLens · Built by Swapnil Padhi · MIT License</span>
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
