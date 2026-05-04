import { useCallback, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { MessageSquare, Github, Linkedin, Info } from 'lucide-react'
import ChatInput from '../components/ChatInput'
import ChatMessage from '../components/ChatMessage'
import Sidebar from '../components/Sidebar'
import AboutModal from '../components/AboutModal'
import { WS_URL } from '../lib/config'
import {
  generateMessageId,
  type ChatMessage as ChatMessageType,
  type ReasoningStep,
  type Source,
  type WsEvent,
  type WsStatus,
  type WsAnswer,
} from '../lib/api'

const EXAMPLE_QUERIES = [
  "What were NVIDIA's revenue drivers in their FY2026 10-K?",
  "Compare Snowflake's revenue growth from FY2023 to FY2026",
  "What are Tesla's main risk factors from their FY2025 10-K?",
  "How did Meta's capital expenditures change from FY2024 to FY2025?",
  "What is Cisco's segment revenue breakdown in FY2025?",
  "What did IBM say about AI consulting demand in their earnings call?",
]

// FAANG first, then others
const TICKER_LINE = 'AAPL · META · NFLX · GOOGL · MSFT · NVDA · TSLA · IBM · CSCO · SNOW + 17 more'

export default function ChatPage() {
  const [messages, setMessages]             = useState<ChatMessageType[]>([])
  const [sessionId, setSessionId]           = useState<string | null>(null)
  const [sidebarCollapsed, setSidebar]      = useState(false)
  const [isLoading, setIsLoading]           = useState(false)
  const [webSearch, setWebSearch]           = useState(false)
  const [sidebarRefresh, setSidebarRefresh] = useState(0)
  const [loadingSession, setLoadingSession] = useState(false)
  const [sidebarW, setSidebarW]             = useState(224)
  const [showAbout, setShowAbout]           = useState(false)

  // Refs used inside WS onmessage to avoid stale closures
  const ws           = useRef<WebSocket | null>(null)
  const bottomRef    = useRef<HTMLDivElement>(null)
  const assistantId  = useRef<string | null>(null)
  const sessionIdRef = useRef<string | null>(null)  // mirrors sessionId state
  const webSearchRef = useRef<boolean>(false)        // mirrors webSearch state

  // Keep refs in sync with state
  useEffect(() => { sessionIdRef.current = sessionId }, [sessionId])
  useEffect(() => { webSearchRef.current = webSearch }, [webSearch])

  // ── WebSocket lifecycle ──────────────────────────────────────────────────

  const connect = useCallback((sid?: string) => {
    ws.current?.close()
    const url = sid ? `${WS_URL}?session_id=${sid}` : WS_URL
    const socket = new WebSocket(url)

    socket.onopen = () => {
      socket.send(JSON.stringify({ type: 'ping' }))
    }

    socket.onmessage = (e) => {
      let data: WsEvent
      try {
        data = JSON.parse(e.data)
      } catch {
        return
      }

      if (data.type === 'pong') return

      if (data.type === 'ack') {
        if (!sessionIdRef.current) {
          const newSid = (data as any).session_id
          setSessionId(newSid)
          sessionIdRef.current = newSid
        }
        return
      }

      if (data.type === 'cancelled') {
        setIsLoading(false)
        const aid = assistantId.current
        if (aid) {
          setMessages(prev => prev.map(m =>
            m.id === aid
              ? { ...m, content: '> ⏹ Generation stopped by user.', isStreaming: false }
              : m
          ))
          assistantId.current = null
        }
        return
      }

      if (data.type === 'status') {
        const d = data as WsStatus
        const step: ReasoningStep = { step: d.step, message: d.message, chunks: d.chunks }
        const aid = assistantId.current
        if (aid) {
          setMessages(prev => prev.map(m =>
            m.id === aid
              ? { ...m, reasoning: [...(m.reasoning ?? []), step] }
              : m
          ))
        }
        return
      }

      if ((data as any).type === 'token') {
        const token: string = (data as any).token
        const aid = assistantId.current
        if (aid && token) {
          setMessages(prev => prev.map(m =>
            m.id === aid
              ? { ...m, content: (m.content ?? '') + token }
              : m
          ))
        }
        return
      }

      if (data.type === 'answer') {
        const d = data as WsAnswer
        setIsLoading(false)
        const aid = assistantId.current
        if (aid) {
          setMessages(prev => prev.map(m =>
            m.id === aid
              ? {
                  ...m,
                  content:    d.answer,
                  sources:    d.citations as Source[],
                  confidence: d.confidence,
                  reasoning:  d.reasoning ?? m.reasoning ?? [],
                  isStreaming: false,
                }
              : m
          ))
          assistantId.current = null
        }
        setSidebarRefresh(n => n + 1)
        return
      }

      if (data.type === 'error') {
        setIsLoading(false)
        const aid = assistantId.current
        if (aid) {
          setMessages(prev => prev.map(m =>
            m.id === aid
              ? { ...m, content: `> ⚠ Error: ${(data as any).detail}`, isStreaming: false }
              : m
          ))
          assistantId.current = null
        }
      }
    }

    socket.onerror = () => {
      setIsLoading(false)
      const aid = assistantId.current
      if (aid) {
        setMessages(prev => prev.map(m =>
          m.id === aid
            ? { ...m, isStreaming: false }
            : m
        ))
        assistantId.current = null
      }
    }

    ws.current = socket
  }, [])

  useEffect(() => {
    connect()
    return () => ws.current?.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── Stop inference ───────────────────────────────────────────────────────

  const stopInference = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ type: 'cancel' }))
    } else {
      setIsLoading(false)
      const aid = assistantId.current
      if (aid) {
        setMessages(prev => prev.map(m =>
          m.id === aid
            ? { ...m, content: '> ⏹ Generation stopped by user.', isStreaming: false }
            : m
        ))
        assistantId.current = null
      }
    }
  }, [])

  // ── Send ────────────────────────────────────────────────────────────────

  const sendMessage = useCallback((text: string) => {
    if (isLoading) return
    if (!ws.current || ws.current.readyState !== WebSocket.OPEN) {
      connect(sessionIdRef.current ?? undefined)
      setTimeout(() => {
        if (ws.current?.readyState === WebSocket.OPEN) {
          dispatchQuery(text)
        }
      }, 300)
      return
    }
    dispatchQuery(text)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading])

  const dispatchQuery = useCallback((text: string) => {
    const userMsg: ChatMessageType = {
      id: generateMessageId(),
      role: 'user',
      content: text,
      timestamp: new Date(),
    }
    const aId = generateMessageId()
    assistantId.current = aId
    const assistantMsg: ChatMessageType = {
      id: aId,
      role: 'assistant',
      content: '',
      reasoning: [],
      sources: [],
      isStreaming: true,
      timestamp: new Date(),
    }

    setMessages(prev => [...prev, userMsg, assistantMsg])
    setIsLoading(true)

    ws.current?.send(JSON.stringify({
      type:       'query',
      question:   text,
      session_id: sessionIdRef.current ?? undefined,
      web_search: webSearchRef.current,   // ref avoids stale closure when sendMessage is cached
    }))
  }, [])

  // ── Session management ───────────────────────────────────────────────────

  const startNewChat = useCallback(() => {
    setMessages([])
    setSessionId(null)
    sessionIdRef.current = null
    setIsLoading(false)
    assistantId.current = null
    connect()
  }, [connect])

  const handleSelectSession = useCallback((id: string) => {
    if (isLoading) return
    setSessionId(id)
    sessionIdRef.current = id
    setMessages([])
    setLoadingSession(true)
    connect(id)

    fetch(`/sessions/${id}`)
      .then(r => r.json())
      .then(data => {
        if (data.messages) {
          const msgs: ChatMessageType[] = data.messages.map((m: any) => {
            const meta = typeof m.metadata === 'string'
              ? JSON.parse(m.metadata)
              : (m.metadata || {})
            return {
              id:          generateMessageId(),
              role:        m.role,
              content:     m.content,
              timestamp:   new Date(m.created_at),
              reasoning:   meta.reasoning ?? [],
              sources:     meta.citations ?? [],
              confidence:  meta.confidence,
              isStreaming: false,
            }
          })
          setMessages(msgs)
        }
      })
      .catch(() => setMessages([]))
      .finally(() => setLoadingSession(false))
  }, [connect, isLoading])

  // ── Render ───────────────────────────────────────────────────────────────

  const SIDEBAR_W = sidebarCollapsed ? 56 : sidebarW

  return (
    <div className="min-h-screen bg-[#faf9f7]">
      <AboutModal isOpen={showAbout} onClose={() => setShowAbout(false)} />

      <Sidebar
        isCollapsed={sidebarCollapsed}
        onToggle={() => setSidebar(!sidebarCollapsed)}
        onNewChat={startNewChat}
        onSelectSession={handleSelectSession}
        activeSessionId={sessionId}
        refreshTrigger={sidebarRefresh}
        onWidthChange={setSidebarW}
      />

      <div
        className="min-h-screen flex flex-col transition-all duration-300"
        style={{ paddingLeft: `${SIDEBAR_W}px` }}
      >
        {/* Header */}
        <header className="sticky top-0 z-20 bg-white/90 backdrop-blur border-b border-slate-200">
          <div className="flex items-center justify-between h-12 px-5">
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-semibold text-[#0a1628] tracking-tight">Research</h1>
              {messages.length > 0 && (
                <span className="text-xs text-slate-400 font-mono">
                  {messages.filter(m => m.role === 'user').length}q
                </span>
              )}
            </div>

            {/* Top-right actions */}
            <div className="flex items-center gap-2">
              {messages.length > 0 && !isLoading && (
                <button
                  onClick={startNewChat}
                  className="text-xs text-slate-500 hover:text-[#0a1628] font-medium px-3 py-1.5 hover:bg-slate-100 rounded-lg transition-colors"
                >
                  New session
                </button>
              )}
              <button
                onClick={() => setShowAbout(true)}
                className="flex items-center gap-1 text-xs text-slate-400 hover:text-[#0a1628] px-2 py-1.5 hover:bg-slate-100 rounded-lg transition-colors"
                title="About AlphaLens"
              >
                <Info className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">About</span>
              </button>
              <a
                href="https://github.com/swapnil18800/alphalens"
                target="_blank" rel="noreferrer"
                className="flex items-center gap-1 text-xs text-slate-400 hover:text-[#0a1628] px-2 py-1.5 hover:bg-slate-100 rounded-lg transition-colors"
                title="GitHub"
              >
                <Github className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">GitHub</span>
              </a>
              <a
                href="https://www.linkedin.com/in/swapnilpadhi"
                target="_blank" rel="noreferrer"
                className="flex items-center gap-1 text-xs text-slate-400 hover:text-[#0a1628] px-2 py-1.5 hover:bg-slate-100 rounded-lg transition-colors"
                title="LinkedIn"
              >
                <Linkedin className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">LinkedIn</span>
              </a>
            </div>
          </div>
        </header>

        {/* Chat area */}
        <main className="flex-1 pb-44">
          <div className="max-w-3xl mx-auto px-5">
            {loadingSession ? (
              <div className="flex items-center justify-center min-h-[50vh]">
                <div className="flex items-center gap-3 text-slate-400 text-sm">
                  <div className="w-4 h-4 border-2 border-slate-300 border-t-slate-600 rounded-full animate-spin" />
                  Loading session…
                </div>
              </div>
            ) : messages.length === 0 ? (
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex flex-col items-center justify-center min-h-[calc(100vh-200px)] text-center py-16"
              >
                <div className="w-12 h-12 bg-[#0a1628] rounded-2xl flex items-center justify-center mb-5 shadow-md">
                  <MessageSquare className="w-6 h-6 text-white" />
                </div>
                <h2 className="text-xl font-bold text-[#0a1628] mb-2">AlphaLens Research</h2>
                <p className="text-slate-500 max-w-md mb-2 text-sm leading-relaxed">
                  Ask anything about SEC 10-K filings and earnings transcripts.
                </p>
                <p className="text-xs text-slate-400 mb-10 font-mono">
                  {TICKER_LINE}
                </p>

                <div className="grid sm:grid-cols-2 gap-2 w-full max-w-2xl">
                  {EXAMPLE_QUERIES.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => sendMessage(q)}
                      className="p-3.5 text-left bg-white border border-slate-200 rounded-xl hover:border-slate-300 hover:shadow-sm transition-all text-sm text-slate-600 hover:text-[#0a1628] leading-snug"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </motion.div>
            ) : (
              <div className="py-6 space-y-8">
                {messages.map(m => (
                  <ChatMessage key={m.id} message={m} />
                ))}
                <div ref={bottomRef} />
              </div>
            )}
          </div>
        </main>

        {/* Fixed input + footer */}
        <div
          className="fixed bottom-0 right-0 bg-gradient-to-t from-[#faf9f7] via-[#faf9f7] to-transparent pt-8 pb-3 transition-all duration-300"
          style={{ left: `${SIDEBAR_W}px` }}
        >
          <div className="max-w-3xl mx-auto px-5">
            <ChatInput
              onSend={sendMessage}
              onStop={isLoading ? stopInference : undefined}
              disabled={isLoading}
              placeholder="Ask about SEC filings, earnings, risk factors…"
              webSearch={webSearch}
              onWebSearchToggle={() => setWebSearch(v => !v)}
            />
            <p className="text-center text-xs text-slate-400 mt-2">
              Grounded in SEC filings & earnings transcripts — verify before acting on financial data
            </p>
            <p className="text-center text-[10px] text-slate-300 mt-0.5">
              © 2024 AlphaLens · MIT License · AI may make errors — always verify independently
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
