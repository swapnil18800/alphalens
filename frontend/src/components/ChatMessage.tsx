import { useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  User, ChevronDown, ChevronUp,
  FileText, Table, Newspaper, ExternalLink, Link, X, BookOpen,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import ReasoningTrace from './ReasoningTrace'
import type { ChatMessage as ChatMessageType, Source } from '../lib/api'

interface Props {
  message: ChatMessageType
}

// ── Source type helpers ────────────────────────────────────────────────────

function sourceType(s: Source): 'transcript' | '10k' | 'news' {
  // Check the explicit source field first — most reliable
  const src = String(s.source || '').toLowerCase()
  if (src === 'transcript') return 'transcript'
  if (src === 'news' || s.url) return 'news'
  if (src === '10k' || src === '10-k' || src.includes('10k') || src.includes('sec')) return '10k'
  // Fallback: use metadata heuristics only when source field is absent/generic
  if (s.url) return 'news'
  if (s.section || s.fiscal_year) return '10k'
  // filing_year alone is not enough — transcripts also have a year
  if (s.filing_year && !s.quarter) return '10k'
  return 'transcript'
}

function sourceTitle(s: Source, type: 'transcript' | '10k' | 'news'): string {
  if (type === 'transcript') {
    const co = s.company || s.company_name || s.ticker || 'Unknown'
    const q  = s.quarter ? ` Q${s.quarter}` : ''
    const yr = s.year    ? ` ${s.year}` : ''
    return `${co}${yr}${q}`
  }
  if (type === '10k') {
    const yr = s.filing_year ?? s.fiscal_year ?? ''
    return `${s.ticker ?? 'Unknown'} ${yr ? `FY${yr} ` : ''}10-K`
  }
  return s.title || 'News Article'
}

// ── Citation marker preprocessing ─────────────────────────────────────────
// Converts [1], [TC-1], [10K-1] in markdown to anchor links

function preprocessCitations(text: string, sources: Source[]): string {
  if (!sources.length) return text
  // Map numeric index [1..n] to marker for fallback
  return text.replace(/\[(\d+|TC-?\d+|10[KQ]-?\d+|N\d+)\]/g, (match, inner) => {
    const idx = parseInt(inner.replace(/\D/g, ''), 10)
    if (idx >= 1 && idx <= sources.length) {
      return `[${inner}](#cite-${idx - 1})`
    }
    return match
  })
}

// ── Confidence badge ───────────────────────────────────────────────────────

function ConfidenceBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const cls = pct >= 80
    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
    : pct >= 60
    ? 'bg-amber-50 text-amber-700 border-amber-200'
    : 'bg-red-50 text-red-700 border-red-200'
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${cls}`}>
      {pct}% confidence
    </span>
  )
}

// ── Citation type badge ────────────────────────────────────────────────────

function TypeBadge({ type }: { type: 'transcript' | '10k' | 'news' }) {
  const map = {
    transcript: { icon: <FileText className="w-3 h-3" />, label: 'Transcript' },
    '10k':      { icon: <Table    className="w-3 h-3" />, label: '10-K' },
    news:       { icon: <Newspaper className="w-3 h-3"/>, label: 'News' },
  }
  const { icon, label } = map[type]
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-600">
      {icon}{label}
    </span>
  )
}

// ── Full-text citation panel (slide-in from right) ────────────────────────

function CitationPanel({ source, onClose }: { source: Source | null; onClose: () => void }) {
  if (!source) return null
  const type  = sourceType(source)
  const title = sourceTitle(source, type)
  return (
    <AnimatePresence>
      {source && (
        <motion.div
          initial={{ x: '100%', opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: '100%', opacity: 0 }}
          transition={{ type: 'spring', damping: 28, stiffness: 320 }}
          className="fixed right-0 top-0 bottom-0 w-[400px] max-w-[92vw] bg-white border-l border-slate-200 shadow-2xl z-50 flex flex-col"
        >
          {/* Panel header */}
          <div className="flex items-start gap-3 px-5 py-4 border-b border-slate-200 bg-slate-50">
            <div className="flex-1 min-w-0">
              <TypeBadge type={type} />
              <p className="font-semibold text-[#0a1628] text-sm mt-1.5 leading-snug">{title}</p>
              {source.section && (
                <p className="text-xs text-slate-400 mt-0.5">{source.section}</p>
              )}
            </div>
            <button
              onClick={onClose}
              className="shrink-0 p-1.5 hover:bg-slate-200 rounded-lg transition-colors text-slate-500"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Panel body — full text */}
          <div className="flex-1 overflow-y-auto p-5">
            {source.chunk_text ? (
              <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap font-mono">
                {source.chunk_text}
              </p>
            ) : (
              <p className="text-sm text-slate-400 italic">No preview text available.</p>
            )}
          </div>

          {type === 'news' && source.url && (
            <div className="px-5 py-3 border-t border-slate-200">
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-xs text-indigo-600 hover:underline"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                Open source article
              </a>
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// ── Individual citation card ───────────────────────────────────────────────

function CitationCard({ source, index, highlighted, onViewFull }: {
  source: Source
  index: number
  highlighted: boolean
  onViewFull: (s: Source) => void
}) {
  const type  = sourceType(source)
  const title = sourceTitle(source, type)
  const hasChunk = !!source.chunk_text

  return (
    <div
      id={`cite-card-${index}`}
      className={`rounded-lg border overflow-hidden transition-all border-slate-200 hover:border-slate-300 ${
        highlighted ? 'ring-2 ring-blue-400 ring-offset-1' : ''
      }`}
    >
      <div className="p-3">
        <div className="flex items-start gap-2 justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <TypeBadge type={type} />
              <span className="text-xs font-mono text-slate-400">[{index + 1}]</span>
            </div>
            <p className="font-medium text-[#0a1628] text-sm leading-snug">{title}</p>
            {source.section && (
              <p className="text-xs text-slate-500 mt-0.5">{source.section}</p>
            )}
          </div>

          <div className="flex items-center gap-1 flex-shrink-0 ml-2">
            {type === 'news' && source.url && (
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="p-1.5 text-slate-400 hover:text-[#0a1628] hover:bg-slate-100 rounded transition-colors"
              >
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
            {hasChunk && (
              <button
                onClick={() => onViewFull(source)}
                className="p-1.5 text-slate-400 hover:text-[#0a1628] hover:bg-slate-100 rounded transition-colors"
                title="View full passage"
              >
                <BookOpen className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {hasChunk && (
          <p
            className="mt-2 text-xs text-slate-500 line-clamp-2 leading-relaxed cursor-pointer hover:text-slate-700"
            onClick={() => onViewFull(source)}
          >
            {source.chunk_text!.slice(0, 180)}…
          </p>
        )}
      </div>
    </div>
  )
}

// ── Citations section ──────────────────────────────────────────────────────

function CitationsSection({ sources, highlightedIdx }: {
  sources: Source[]
  highlightedIdx: number | null
}) {
  const [open, setOpen] = useState(false)
  const [activeCitation, setActiveCitation] = useState<Source | null>(null)

  const tenKs       = sources.filter(s => sourceType(s) === '10k')
  const transcripts = sources.filter(s => sourceType(s) === 'transcript')
  const news        = sources.filter(s => sourceType(s) === 'news')

  const parts = [
    tenKs.length       && `${tenKs.length} 10-K`,
    transcripts.length && `${transcripts.length} transcript`,
    news.length        && `${news.length} news`,
  ].filter(Boolean).join(', ')

  return (
    <>
      <div className="mt-4 rounded-lg border border-slate-200 overflow-hidden">
        <button
          onClick={() => setOpen(!open)}
          className="w-full flex items-center justify-between px-4 py-3 bg-slate-50 hover:bg-slate-100 transition-colors"
        >
          <div className="flex items-center gap-2">
            <Link className="w-4 h-4 text-slate-400" />
            <span className="font-medium text-[#0a1628] text-sm">
              {sources.length} source{sources.length !== 1 ? 's' : ''}
            </span>
            <span className="text-sm text-slate-400 font-mono">({parts})</span>
          </div>
          {open ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
        </button>

        <AnimatePresence>
          {open && (
            <motion.div
              initial={{ height: 0 }}
              animate={{ height: 'auto' }}
              exit={{ height: 0 }}
              className="overflow-hidden"
            >
              <div className="p-3 space-y-2 bg-white">
                {sources.map((s, i) => (
                  <CitationCard
                    key={i}
                    source={s}
                    index={i}
                    highlighted={highlightedIdx === i}
                    onViewFull={setActiveCitation}
                  />
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Right-side full-text panel */}
      <CitationPanel source={activeCitation} onClose={() => setActiveCitation(null)} />
    </>
  )
}

// ── Main ChatMessage export ────────────────────────────────────────────────

export default function ChatMessage({ message }: Props) {
  const [highlightedIdx, setHighlightedIdx] = useState<number | null>(null)

  const handleCiteClick = useCallback((idx: number) => {
    setHighlightedIdx(idx)
    setTimeout(() => {
      document.getElementById(`cite-card-${idx}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }, 200)
    setTimeout(() => setHighlightedIdx(null), 2000)
  }, [])

  const isUser   = message.role === 'user'
  const sources  = message.sources  ?? []
  const reasoning = message.reasoning ?? []

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}
    >
      {/* Avatar */}
      <div className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold ${
        isUser ? 'bg-slate-200 text-slate-600' : 'bg-[#0a1628] text-white'
      }`}>
        {isUser ? <User className="w-4 h-4" /> : 'α'}
      </div>

      {/* Body */}
      <div className={`flex-1 min-w-0 ${isUser ? 'flex flex-col items-end' : ''}`}>

        {/* Reasoning trace — only for assistant */}
        {!isUser && (reasoning.length > 0 || message.isStreaming) && (
          <ReasoningTrace steps={reasoning} isStreaming={message.isStreaming} />
        )}

        {/* Bubble */}
        <div className={
          isUser
            ? 'bg-slate-100 text-[#0a1628] rounded-2xl rounded-tr-sm px-4 py-3 max-w-[85%] text-sm'
            : 'w-full'
        }>
          {isUser ? (
            <span className="whitespace-pre-wrap">{message.content}</span>
          ) : (
            <div className="prose prose-slate max-w-none text-[17px]
              prose-headings:text-[#0a1628] prose-headings:font-bold prose-headings:mt-5 prose-headings:mb-2
              prose-h2:text-lg prose-h3:text-base
              prose-p:text-slate-700 prose-p:leading-relaxed prose-p:my-2 prose-p:text-[17px]
              prose-strong:text-[#0a1628] prose-strong:font-bold
              prose-li:text-slate-700 prose-li:my-0.5 prose-li:text-[17px]
              prose-code:text-[#0a1628] prose-code:bg-slate-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:before:content-[''] prose-code:after:content-['']
              prose-pre:bg-[#0a1628] prose-pre:text-slate-100 prose-pre:rounded-lg prose-pre:text-sm
              prose-blockquote:border-l-4 prose-blockquote:border-slate-300 prose-blockquote:bg-slate-50 prose-blockquote:text-slate-600 prose-blockquote:py-1
              prose-table:w-full prose-table:border-collapse prose-table:text-sm
              prose-th:bg-slate-50 prose-th:text-[#0a1628] prose-th:font-semibold prose-th:px-3 prose-th:py-2 prose-th:border prose-th:border-slate-200 prose-th:text-left
              prose-td:px-3 prose-td:py-2 prose-td:border prose-td:border-slate-200 prose-td:text-slate-700
              prose-a:text-indigo-600 prose-a:underline prose-a:underline-offset-2
            ">
              {/* Streaming: show skeleton dots while no content yet */}
              {message.isStreaming && !message.content ? (
                <div className="flex items-center gap-1 py-2">
                  <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:0ms]" />
                  <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:100ms]" />
                  <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce [animation-delay:200ms]" />
                </div>
              ) : (
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    a: ({ href, children }) => {
                      if (href?.startsWith('#cite-')) {
                        const idx = parseInt(href.replace('#cite-', ''), 10)
                        return (
                          <button
                            onClick={() => handleCiteClick(idx)}
                            className="inline-flex items-center justify-center w-5 h-5 mx-0.5 text-[10px] font-semibold rounded-full bg-slate-200 text-slate-600 hover:bg-[#0a1628] hover:text-white cursor-pointer transition-colors align-super -translate-y-0.5"
                          >
                            {idx + 1}
                          </button>
                        )
                      }
                      return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
                    }
                  }}
                >
                  {preprocessCitations(message.content, sources)}
                </ReactMarkdown>
              )}
            </div>
          )}
        </div>

        {/* Confidence + sources — only after streaming done */}
        {!isUser && !message.isStreaming && (
          <>
            {message.confidence != null && message.confidence > 0 && (
              <div className="mt-2">
                <ConfidenceBadge score={message.confidence} />
              </div>
            )}
            {sources.length > 0 && (
              <CitationsSection sources={sources} highlightedIdx={highlightedIdx} />
            )}
          </>
        )}
      </div>
    </motion.div>
  )
}
