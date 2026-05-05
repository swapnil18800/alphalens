import { useCallback, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { MessageSquare, Info } from 'lucide-react'
import ChatInput from '../components/ChatInput'
import ChatMessage from '../components/ChatMessage'
import Sidebar from '../components/Sidebar'
import AboutModal from '../components/AboutModal'
import AuthModal from '../components/AuthModal'
import { WS_URL } from '../lib/config'
import { AUTH_AVAILABLE } from '../lib/config'
import { useAuthStatus } from '../hooks/useAuthStatus'
import { useAnonId } from '../hooks/useAnonId'
import {
  generateMessageId,
  type ChatMessage as ChatMessageType,
  type ReasoningStep,
  type Source,
  type WsEvent,
  type WsStatus,
  type WsAnswer,
} from '../lib/api'

// Curated from evals/qa_eval/docs/DEMO_QUESTION_GUIDE.md (top-tier reliable PASSes)
const EXAMPLE_QUERIES = [
  "What did Netflix management say about subscriber growth and content strategy in FY2024 earnings calls?",
  "Trace Amazon Web Services revenue growth and operating margin from FY2022 to FY2024 based on annual reports.",
  "Break down Microsoft's revenue by its three reportable segments and describe each segment.",
  "What were Broadcom's FY2024 revenue segments after completing the VMware acquisition?",
  "What does Microsoft's most recent 10-K say about Azure growth, and what 2026 Copilot announcements have been made?",
  "What does SpaceX's FY2024 10-K report as its total revenue and operating margin?",
]

const TICKER_LINE = 'AAPL · META · NFLX · GOOGL · MSFT · NVDA · TSLA · IBM · CSCO · SNOW + 17 more'

function GithubIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12Z" />
    </svg>
  )
}

export default function ChatPage() {
  const { isSignedIn, getToken, user, signOut } = useAuthStatus()
  const anonId = useAnonId()

  const [messages, setMessages]             = useState<ChatMessageType[]>([])
  const [sessionId, setSessionId]           = useState<string | null>(null)
  const [sidebarCollapsed, setSidebar]      = useState(false)
  const [isLoading, setIsLoading]           = useState(false)
  const [webSearch, setWebSearch]           = useState(false)
  const [sidebarRefresh, setSidebarRefresh] = useState(0)
  const [loadingSession, setLoadingSession] = useState(false)
  const [sidebarW, setSidebarW]             = useState(224)
  const [showAbout, setShowAbout]           = useState(false)
  const [showAuth, setShowAuth]             = useState(false)
  const [profileOpen, setProfileOpen]       = useState(false)

  const ws           = useRef<WebSocket | null>(null)
  const bottomRef    = useRef<HTMLDivElement>(null)
  const assistantId  = useRef<string | null>(null)
  const sessionIdRef = useRef<string | null>(null)
  const webSearchRef = useRef<boolean>(false)
  const getTokenRef  = useRef(getToken)
  const profileRef   = useRef<HTMLDivElement>(null)

  useEffect(() => { sessionIdRef.current = sessionId }, [sessionId])
  useEffect(() => { webSearchRef.current = webSearch }, [webSearch])
  useEffect(() => { getTokenRef.current = getToken }, [getToken])

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

  // ── WebSocket lifecycle ──────────────────────────────────────────────────

  const connect = useCallback(async (sid?: string) => {
    ws.current?.close()
    let token: string | null = null
    try { token = await getTokenRef.current?.() ?? null } catch { /* anonymous */ }

    const params = new URLSearchParams()
    if (sid) params.set('session_id', sid)
    if (token) params.set('token', token)
    // Pass anon_id only when not authenticated, so backend can scope sessions
    if (!token) params.set('anon_id', anonId)
    const url = `${WS_URL}?${params.toString()}`
    const socket = new WebSocket(url)

    socket.onopen = () => socket.send(JSON.stringify({ type: 'ping' }))

    socket.onmessage = (e) => {
      let data: WsEvent
      try { data = JSON.parse(e.data) } catch { return }

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
            m.id === aid ? { ...m, content: '**Generation stopped.**', isStreaming: false } : m
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
            m.id === aid ? { ...m, reasoning: [...(m.reasoning ?? []), step] } : m
          ))
        }
        return
      }

      if ((data as any).type === 'session_updated') {
        // Smart title was generated by background task — refresh sidebar
        setSidebarRefresh(n => n + 1)
        return
      }

      if ((data as any).type === 'token') {
        const tok: string = (data as any).token
        const aid = assistantId.current
        if (aid && tok) {
          setMessages(prev => prev.map(m =>
            m.id === aid ? { ...m, content: (m.content ?? '') + tok } : m
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
              ? { ...m, content: d.answer, sources: d.citations as Source[], confidence: d.confidence, reasoning: d.reasoning ?? m.reasoning ?? [], isStreaming: false }
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
            m.id === aid ? { ...m, content: `> ⚠ Error: ${(data as any).detail}`, isStreaming: false } : m
          ))
          assistantId.current = null
        }
      }
    }

    socket.onerror = () => {
      setIsLoading(false)
      const aid = assistantId.current
      if (aid) {
        setMessages(prev => prev.map(m => m.id === aid ? { ...m, isStreaming: false } : m))
        assistantId.current = null
      }
    }

    ws.current = socket
  }, [anonId])

  useEffect(() => {
    connect()
    return () => ws.current?.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── Stop ─────────────────────────────────────────────────────────────────

  const stopInference = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ type: 'cancel' }))
    } else {
      setIsLoading(false)
      const aid = assistantId.current
      if (aid) {
        setMessages(prev => prev.map(m =>
          m.id === aid ? { ...m, content: '> ⏹ Generation stopped by user.', isStreaming: false } : m
        ))
        assistantId.current = null
      }
    }
  }, [])

  // ── Send ─────────────────────────────────────────────────────────────────

  const dispatchQuery = useCallback((text: string) => {
    const userMsg: ChatMessageType = { id: generateMessageId(), role: 'user', content: text, timestamp: new Date() }
    const aId = generateMessageId()
    assistantId.current = aId
    const assistantMsg: ChatMessageType = { id: aId, role: 'assistant', content: '', reasoning: [], sources: [], isStreaming: true, timestamp: new Date() }
    setMessages(prev => [...prev, userMsg, assistantMsg])
    setIsLoading(true)
    ws.current?.send(JSON.stringify({ type: 'query', question: text, session_id: sessionIdRef.current ?? undefined, web_search: webSearchRef.current }))
  }, [])

  const sendMessage = useCallback((text: string) => {
    if (isLoading) return
    if (!ws.current || ws.current.readyState !== WebSocket.OPEN) {
      connect(sessionIdRef.current ?? undefined)
      setTimeout(() => { if (ws.current?.readyState === WebSocket.OPEN) dispatchQuery(text) }, 300)
      return
    }
    dispatchQuery(text)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading])

  // ── Session management ────────────────────────────────────────────────────

  const startNewChat = useCallback(() => {
    setMessages([]); setSessionId(null); sessionIdRef.current = null
    setIsLoading(false); assistantId.current = null; connect()
  }, [connect])

  const handleSelectSession = useCallback((id: string) => {
    if (isLoading) return
    setSessionId(id); sessionIdRef.current = id
    setMessages([]); setLoadingSession(true); connect(id)

    const headers: Record<string, string> = {}
    if (!isSignedIn) headers['X-Anon-Id'] = anonId

    fetch(`/sessions/${id}`, { headers })
      .then(r => r.json())
      .then(data => {
        if (data.messages) {
          const msgs: ChatMessageType[] = data.messages.map((m: any) => {
            const meta = typeof m.metadata === 'string' ? JSON.parse(m.metadata) : (m.metadata || {})
            return { id: generateMessageId(), role: m.role, content: m.content, timestamp: new Date(m.created_at), reasoning: meta.reasoning ?? [], sources: meta.citations ?? [], confidence: meta.confidence, isStreaming: false }
          })
          setMessages(msgs)
        }
      })
      .catch(() => setMessages([]))
      .finally(() => setLoadingSession(false))
  }, [connect, isLoading, isSignedIn, anonId])

  // ── Render ────────────────────────────────────────────────────────────────

  const SIDEBAR_W = sidebarCollapsed ? 56 : sidebarW
  const u: any = user
  const firstName  = u?.firstName ?? ''
  const lastName   = u?.lastName  ?? ''
  const fullName   = `${firstName} ${lastName}`.trim() || u?.fullName || u?.username || 'Account'
  const userInitial = (firstName?.[0] || u?.emailAddresses?.[0]?.emailAddress?.[0] || 'U').toUpperCase()

  return (
    <div className="min-h-screen bg-[#fafafa]">
      <AboutModal isOpen={showAbout} onClose={() => setShowAbout(false)} />
      <AuthModal isOpen={showAuth} onClose={() => setShowAuth(false)} />

      <Sidebar
        isCollapsed={sidebarCollapsed}
        onToggle={() => setSidebar(!sidebarCollapsed)}
        onNewChat={startNewChat}
        onSelectSession={handleSelectSession}
        activeSessionId={sessionId}
        refreshTrigger={sidebarRefresh}
        onWidthChange={setSidebarW}
        anonId={isSignedIn ? undefined : anonId}
      />

      <div className="min-h-screen flex flex-col transition-all duration-300" style={{ paddingLeft: `${SIDEBAR_W}px` }}>
        {/* Header */}
        <header className="sticky top-0 z-20 bg-white/90 backdrop-blur border-b border-neutral-200">
          <div className="flex items-center justify-between h-12 px-5">
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-semibold text-[#000000] tracking-tight">Research</h1>
              {messages.length > 0 && (
                <span className="text-xs text-neutral-400 font-mono">
                  {messages.filter(m => m.role === 'user').length}q
                </span>
              )}
            </div>

            {/* Top-right actions */}
            <div className="flex items-center gap-1.5">
              {messages.length > 0 && !isLoading && (
                <button
                  onClick={startNewChat}
                  className="text-xs text-neutral-500 hover:text-[#000000] font-medium px-3 py-1.5 hover:bg-neutral-100 rounded-lg transition-colors"
                >
                  New session
                </button>
              )}
              <button
                onClick={() => setShowAbout(true)}
                className="flex items-center gap-1 text-xs text-neutral-400 hover:text-[#000000] px-2 py-1.5 hover:bg-neutral-100 rounded-lg transition-colors"
                title="About AlphaLens"
              >
                <Info className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">About</span>
              </button>
              <a
                href="https://github.com/swapnil18800/alphalens"
                target="_blank" rel="noreferrer"
                className="flex items-center text-neutral-400 hover:text-[#000000] px-2 py-1.5 hover:bg-neutral-100 rounded-lg transition-colors"
                title="GitHub"
              >
                <GithubIcon className="w-3.5 h-3.5" />
              </a>

              {/* Auth: sign in button or profile icon */}
              {AUTH_AVAILABLE && !isSignedIn && (
                <button
                  onClick={() => setShowAuth(true)}
                  className="text-xs text-neutral-700 hover:bg-black hover:text-white font-medium px-3 py-1.5 rounded-lg transition-colors border border-black/15"
                >
                  Sign In
                </button>
              )}

              {AUTH_AVAILABLE && isSignedIn && (
                <div className="relative" ref={profileRef}>
                  <button
                    onClick={() => setProfileOpen(v => !v)}
                    className="w-8 h-8 rounded-full overflow-hidden bg-black flex items-center justify-center text-white text-xs font-bold hover:opacity-80 transition-opacity ring-1 ring-black/10"
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
            </div>
          </div>
        </header>

        {/* Chat area */}
        <main className="flex-1 pb-44">
          <div className="max-w-3xl mx-auto px-5">
            {loadingSession ? (
              <div className="flex items-center justify-center min-h-[50vh]">
                <div className="flex items-center gap-3 text-neutral-400 text-sm">
                  <div className="w-4 h-4 border-2 border-neutral-300 border-t-black rounded-full animate-spin" />
                  Loading session…
                </div>
              </div>
            ) : messages.length === 0 ? (
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex flex-col items-center justify-center min-h-[calc(100vh-200px)] text-center py-16"
              >
                <div className="w-12 h-12 bg-[#000000] rounded-2xl flex items-center justify-center mb-5 shadow-md">
                  <MessageSquare className="w-6 h-6 text-white" />
                </div>
                <h2 className="text-xl font-bold text-[#000000] mb-2">AlphaLens Research</h2>
                <p className="text-neutral-500 max-w-md mb-2 text-sm leading-relaxed">
                  Ask anything about SEC 10-K filings and earnings transcripts.
                </p>
                <p className="text-xs text-neutral-400 mb-10 font-mono">{TICKER_LINE}</p>

                <div className="grid sm:grid-cols-2 gap-2 w-full max-w-2xl">
                  {EXAMPLE_QUERIES.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => sendMessage(q)}
                      className="p-3.5 text-left bg-white border border-neutral-200 rounded-xl hover:border-neutral-300 hover:shadow-sm transition-all text-sm text-neutral-600 hover:text-[#000000] leading-snug"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </motion.div>
            ) : (
              <div className="py-6 space-y-8">
                {messages.map(m => <ChatMessage key={m.id} message={m} />)}
                <div ref={bottomRef} />
              </div>
            )}
          </div>
        </main>

        {/* Fixed input */}
        <div
          className="fixed bottom-0 right-0 bg-gradient-to-t from-[#fafafa] via-[#fafafa] to-transparent pt-8 pb-3 transition-all duration-300"
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
            <p className="text-center text-xs text-neutral-400 mt-2">
              Grounded in SEC filings & earnings transcripts — verify before acting on financial data
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
