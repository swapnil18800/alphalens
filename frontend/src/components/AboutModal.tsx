import { motion, AnimatePresence } from 'framer-motion'
import { X } from 'lucide-react'
import { useEffect } from 'react'

interface AboutModalProps {
  isOpen: boolean
  onClose: () => void
}

function LinkedinIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
    </svg>
  )
}

export default function AboutModal({ isOpen, onClose }: AboutModalProps) {
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
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
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />

          <motion.div
            initial={{ scale: 0.96, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.96, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="relative w-full max-w-md bg-white rounded-2xl shadow-2xl border border-black/8 overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-5 border-b border-black/8">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 bg-black rounded-lg flex items-center justify-center text-white font-black text-sm">
                  α
                </div>
                <h2 className="text-base font-bold text-black">About AlphaLens</h2>
              </div>
              <button
                onClick={onClose}
                className="p-1.5 text-neutral-400 hover:text-black hover:bg-neutral-100 rounded-lg transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Content */}
            <div className="px-6 py-5 space-y-5">
              <p className="text-neutral-600 text-sm leading-relaxed">
                AI equity research copilot providing quick insights from U.S. public markets data.
              </p>

              <div>
                <p className="text-xs text-neutral-400 mb-0.5 font-medium uppercase tracking-wide">Created by</p>
                <p className="font-semibold text-black text-base">Swapnil Padhi</p>
                <a
                  href="https://www.linkedin.com/in/swapnilpadhi/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-sm text-neutral-600 hover:text-black font-medium transition-colors mt-1.5"
                >
                  <LinkedinIcon className="w-4 h-4" />
                  LinkedIn
                </a>
              </div>

              <div className="h-px bg-black/8" />

              <p className="text-sm text-neutral-600 leading-relaxed">
                AlphaLens is a focused exploration of applying agentic RAG to equity research — combining
                query decomposition, retrieval over SEC filings and earnings transcripts, and structured
                reasoning for complex financial questions. It's now open-sourced for anyone interested in
                building on or adapting the system. It was an incredibly valuable journey. Feel free to use and contribute!
              </p>

              <button
                onClick={onClose}
                className="w-full bg-black hover:bg-neutral-800 text-white font-semibold py-2.5 rounded-xl transition-colors text-sm"
              >
                Close
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
