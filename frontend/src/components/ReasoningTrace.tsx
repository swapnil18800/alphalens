import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ChevronDown, ChevronRight, Loader2,
  Search, FileText, Zap, CheckCircle, RotateCcw, RefreshCw, Flag,
  GitBranch, X, BookOpen,
} from 'lucide-react'
import type { ReasoningStep } from '../lib/api'

// ── Step config ────────────────────────────────────────────────────────────

const STEP_CONFIG: Record<string, { icon: React.ElementType; label: string }> = {
  analyze:      { icon: Search,       label: 'Analyzing'   },
  decompose:    { icon: GitBranch,    label: 'Decomposed'  },
  search:       { icon: FileText,     label: 'Searching'   },
  search_retry: { icon: RefreshCw,    label: 'Retrying'    },
  generate:     { icon: Zap,          label: 'Generating'  },
  evaluate:     { icon: CheckCircle,  label: 'Evaluating'  },
  rewrite:      { icon: RotateCcw,    label: 'Rewriting'   },
  finalize:     { icon: Flag,         label: 'Done'        },
}

interface Props {
  steps: ReasoningStep[]
  isStreaming?: boolean
}

type ChunkPreview = NonNullable<ReasoningStep['chunks']>[0]

// ── Right-side chunk panel (mirrors CitationPanel) ─────────────────────────

function ChunkPanel({ chunk, onClose }: { chunk: ChunkPreview | null; onClose: () => void }) {
  if (!chunk) return null

  const sourceLabel =
    chunk.source === 'transcript' ? 'Transcript' :
    chunk.source === 'news'       ? 'Web / News' : '10-K'

  const title =
    chunk.source === 'news'
      ? 'News Article'
      : `${chunk.ticker}${chunk.year ? ` ${chunk.year}` : ''} ${sourceLabel}`

  return (
    <AnimatePresence>
      {chunk && (
        <motion.div
          initial={{ x: '100%', opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: '100%', opacity: 0 }}
          transition={{ type: 'spring', damping: 28, stiffness: 320 }}
          className="fixed right-0 top-0 bottom-0 w-[380px] max-w-[92vw] bg-white border-l border-slate-200 shadow-2xl z-[60] flex flex-col"
        >
          {/* Panel header */}
          <div className="flex items-start gap-3 px-5 py-4 border-b border-slate-200 bg-slate-50 shrink-0">
            <div className="flex-1 min-w-0">
              <span className={`inline-flex items-center text-[10px] font-bold px-1.5 py-0.5 rounded mb-1.5 ${
                chunk.source === 'transcript' ? 'bg-blue-50 text-blue-600'
                : chunk.source === 'news'     ? 'bg-emerald-50 text-emerald-600'
                : 'bg-slate-100 text-slate-500'
              }`}>
                {sourceLabel}
              </span>
              <p className="font-semibold text-[#0a1628] text-sm leading-snug">{title}</p>
              {chunk.section && (
                <p className="text-xs text-slate-400 mt-0.5">{chunk.section}</p>
              )}
            </div>
            <button
              onClick={onClose}
              className="shrink-0 p-1.5 hover:bg-slate-200 rounded-lg transition-colors text-slate-500"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Panel body */}
          <div className="flex-1 overflow-y-auto p-5">
            {chunk.text ? (
              <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap font-mono">
                {chunk.text}
              </p>
            ) : (
              <p className="text-sm text-slate-400 italic">No preview text available.</p>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// ── Compact chunk card — click opens right panel ───────────────────────────

function ChunkCard({
  chunk,
  onViewFull,
}: {
  chunk: ChunkPreview
  onViewFull: (c: ChunkPreview) => void
}) {
  const sourceLabel =
    chunk.source === 'transcript' ? 'TC' :
    chunk.source === 'news'       ? 'WEB' : '10K'

  const label =
    chunk.source === 'news'
      ? 'News'
      : `${chunk.ticker}${chunk.year ? ` ${chunk.year}` : ''}`

  return (
    <button
      onClick={() => onViewFull(chunk)}
      title={`View passage: ${label}`}
      className="inline-flex items-center gap-1.5 border border-slate-200 rounded-lg px-2.5 py-1.5 bg-white hover:bg-slate-50 hover:border-slate-300 transition-colors max-w-[200px]"
    >
      <span className={`text-[9px] font-bold px-1 py-0.5 rounded shrink-0 ${
        chunk.source === 'transcript' ? 'bg-blue-50 text-blue-600'
        : chunk.source === 'news'    ? 'bg-emerald-50 text-emerald-600'
        : 'bg-slate-100 text-slate-500'
      }`}>
        {sourceLabel}
      </span>
      <span className="text-[11px] text-slate-700 font-medium truncate">{label}</span>
      <BookOpen className="w-2.5 h-2.5 text-slate-300 shrink-0" />
    </button>
  )
}

// ── Main ReasoningTrace ────────────────────────────────────────────────────

export default function ReasoningTrace({ steps, isStreaming }: Props) {
  const [collapsed, setCollapsed]         = useState(false)
  const [activeChunk, setActiveChunk]     = useState<ChunkPreview | null>(null)

  if (steps.length === 0 && !isStreaming) return null

  // Accumulate all steps in arrival order — search/search_retry/evaluate/rewrite
  // each represent distinct pipeline events and must stay chronological so the
  // trace reads: search → generate → evaluate(low) → rewrite → retry → evaluate(final)
  // Only collapse analyze/decompose/finalize which are single-occurrence bookends.
  const SINGLE_OCCURRENCE = new Set(['analyze', 'decompose', 'finalize'])
  const deduped = steps.reduce<ReasoningStep[]>((acc, s) => {
    if (SINGLE_OCCURRENCE.has(s.step)) {
      const idx = acc.findIndex(x => x.step === s.step)
      if (idx >= 0) { const u = [...acc]; u[idx] = s; return u }
    }
    return [...acc, s]
  }, [])

  const last   = steps[steps.length - 1]
  const isDone = last?.step === 'finalize' && !isStreaming

  return (
    <>
      <div className="mb-3 rounded-xl border border-slate-200 bg-white overflow-hidden text-sm shadow-sm">
        {/* Header */}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-slate-50 transition-colors text-left"
        >
          {collapsed
            ? <ChevronRight className="w-3.5 h-3.5 text-slate-300 shrink-0" />
            : <ChevronDown  className="w-3.5 h-3.5 text-slate-300 shrink-0" />
          }
          <span className="flex-1 text-slate-500 text-xs truncate">
            {collapsed
              ? (isDone ? last.message : (last?.message ?? 'Processing…'))
              : 'Reasoning trace'
            }
          </span>
          {isStreaming && (
            <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-400 shrink-0" />
          )}
          {!isStreaming && deduped.length > 0 && (
            <span className="text-[10px] text-slate-300">{deduped.length} steps</span>
          )}
        </button>

        <AnimatePresence initial={false}>
          {!collapsed && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="overflow-hidden"
            >
              <div className="px-3 pb-3 pt-1 space-y-2.5 border-t border-slate-100">
                {deduped.map((s, i) => {
                  const cfg    = STEP_CONFIG[s.step]
                  const Icon   = cfg?.icon
                  const isLast = i === deduped.length - 1
                  const hasChunks = s.chunks && s.chunks.length > 0

                  return (
                    <div key={`${s.step}-${i}`}>
                      <motion.div
                        initial={isLast ? { opacity: 0, x: -4 } : false}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.12 }}
                        className="flex items-start gap-2.5"
                      >
                        {/* Icon */}
                        <div className="shrink-0 w-5 h-5 rounded flex items-center justify-center mt-0.5 bg-slate-50">
                          {Icon
                            ? <Icon className="w-3 h-3 text-slate-500" />
                            : <span className="text-[10px] text-slate-400">▸</span>
                          }
                        </div>

                        <div className="flex-1 min-w-0">
                          {cfg && (
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mr-1.5">
                              {cfg.label}
                            </span>
                          )}
                          <span className="text-xs text-slate-500 leading-snug">{s.message}</span>
                        </div>

                        {/* Spinner only on active last step */}
                        {isStreaming && isLast && (
                          <Loader2 className="w-3 h-3 animate-spin text-slate-400 shrink-0 mt-1" />
                        )}
                      </motion.div>

                      {/* Chunk cards — scrollable strip showing all citations */}
                      {hasChunks && (
                        <div className="ml-7 mt-2 max-h-44 overflow-y-auto pr-1">
                          <div className="flex flex-wrap gap-1.5">
                            {s.chunks!.map((chunk, ci) => (
                              <ChunkCard key={ci} chunk={chunk} onViewFull={setActiveChunk} />
                            ))}
                          </div>
                          <p className="text-[10px] text-neutral-400 mt-2 px-0.5">
                            {s.chunks!.length} {s.chunks!.length === 1 ? 'citation' : 'citations'} · click to inspect
                          </p>
                        </div>
                      )}
                    </div>
                  )
                })}

                {isStreaming && deduped.length === 0 && (
                  <div className="flex items-center gap-2 text-slate-400">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    <span className="text-xs">Starting…</span>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Right-side panel for chunk text — shared across all cards */}
      <ChunkPanel chunk={activeChunk} onClose={() => setActiveChunk(null)} />
    </>
  )
}
