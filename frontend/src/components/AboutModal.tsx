import { motion, AnimatePresence } from 'framer-motion'
import { X, Github, Linkedin } from 'lucide-react'
import { useEffect } from 'react'

interface AboutModalProps {
  isOpen: boolean
  onClose: () => void
}

export default function AboutModal({ isOpen, onClose }: AboutModalProps) {
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    if (isOpen) {
      document.addEventListener('keydown', handleEscape)
      document.body.style.overflow = 'hidden'
    }
    return () => {
      document.removeEventListener('keydown', handleEscape)
      document.body.style.overflow = ''
    }
  }, [isOpen, onClose])

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[9999] flex items-center justify-center p-4"
          onClick={onClose}
        >
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="relative w-full max-w-md bg-white rounded-2xl shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-gradient-to-r from-slate-50 to-white">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 bg-[#0a1628] rounded-lg flex items-center justify-center text-white font-black text-sm">
                  α
                </div>
                <h2 className="text-lg font-bold text-slate-900">About AlphaLens</h2>
              </div>
              <button
                onClick={onClose}
                className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Content */}
            <div className="px-6 py-5 space-y-4">
              <p className="text-slate-600 text-sm leading-relaxed">
                Agentic AI equity research copilot — grounded in SEC 10-K filings and earnings call
                transcripts for 27 major public companies. Ask questions, get cited, confidence-scored answers.
              </p>

              <div className="p-4 bg-slate-50 rounded-xl text-sm text-slate-600 leading-relaxed">
                <strong className="text-slate-800">Stack:</strong> FastAPI · LangGraph · pgvector · Cerebras/OpenAI ·
                React · PostgreSQL. Tavily web search. Hybrid BM25 + vector search with cross-encoder RRF reranking and semantic response cache.
              </div>

              <div>
                <p className="text-xs text-slate-400 mb-0.5">Created by</p>
                <p className="font-semibold text-slate-900">Swapnil Padhi</p>
              </div>

              <div className="flex items-center gap-5">
                <a
                  href="https://github.com/swapnil18800/alphalens"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-sm text-slate-600 hover:text-[#0a1628] font-medium transition-colors"
                >
                  <Github className="w-4 h-4" /> GitHub
                </a>
                <a
                  href="https://www.linkedin.com/in/swapnilpadhi/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-sm text-slate-600 hover:text-[#0a1628] font-medium transition-colors"
                >
                  <Linkedin className="w-4 h-4" /> LinkedIn
                </a>
              </div>

              <div className="pt-3 border-t border-slate-200">
                <p className="text-xs text-slate-400 leading-relaxed">
                  Open source · MIT License ·{' '}
                  <span className="text-amber-600 font-medium">AI responses may contain errors.</span>{' '}
                  Always verify financial data independently before making investment decisions.
                </p>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
