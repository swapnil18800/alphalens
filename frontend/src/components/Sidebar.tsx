import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { PlusCircle, MessageSquare, ChevronLeft, ChevronRight, Trash2 } from 'lucide-react'
import { listSessions, type Session } from '../lib/api'

const MIN_W = 160
const MAX_W = 360
const COLLAPSED_W = 56
const DEFAULT_W = 224

interface Props {
  isCollapsed: boolean
  onToggle: () => void
  onNewChat: () => void
  onSelectSession: (id: string) => void
  activeSessionId?: string | null
  refreshTrigger?: number
  onWidthChange?: (w: number) => void
}

export default function Sidebar({
  isCollapsed, onToggle, onNewChat, onSelectSession, activeSessionId, refreshTrigger, onWidthChange,
}: Props) {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<Session[]>([])
  const [width, setWidth] = useState(DEFAULT_W)
  const dragging = useRef(false)
  const startX   = useRef(0)
  const startW   = useRef(DEFAULT_W)

  const loadSessions = useCallback(() => {
    listSessions()
      .then(r => setSessions(r.sessions))
      .catch(() => {})
  }, [])

  const deleteSession = useCallback(async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    try {
      await fetch(`/sessions/${id}`, { method: 'DELETE' })
      setSessions(prev => prev.filter(s => s.id !== id))
    } catch {}
  }, [])

  useEffect(() => { loadSessions() }, [loadSessions])
  useEffect(() => {
    if (refreshTrigger !== undefined && refreshTrigger > 0) loadSessions()
  }, [refreshTrigger, loadSessions])

  // Drag-to-resize handle
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (isCollapsed) return
    dragging.current = true
    startX.current   = e.clientX
    startW.current   = width
    e.preventDefault()
  }, [isCollapsed, width])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return
      const delta = e.clientX - startX.current
      const next  = Math.min(MAX_W, Math.max(MIN_W, startW.current + delta))
      setWidth(next)
      onWidthChange?.(next)
    }
    const onUp = () => { dragging.current = false }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  const sidebarW = isCollapsed ? COLLAPSED_W : width

  return (
    <aside
      className="fixed left-0 top-0 h-full bg-[#0a1628] text-slate-100 flex flex-col z-30 select-none"
      style={{ width: sidebarW, transition: dragging.current ? 'none' : 'width 0.25s ease' }}
    >
      {/* Logo + collapse */}
      <div className="flex items-center justify-between px-3 py-4 border-b border-slate-700/50 shrink-0">
        {!isCollapsed && (
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 hover:text-slate-300 transition-colors truncate"
          >
            <div className="w-6 h-6 bg-indigo-500 rounded-md flex items-center justify-center text-white text-xs font-black shrink-0">
              α
            </div>
            <span className="text-sm font-bold text-white tracking-tight">AlphaLens</span>
          </button>
        )}
        <button
          onClick={onToggle}
          className={`p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700/50 transition-colors shrink-0 ${isCollapsed ? 'mx-auto' : ''}`}
          title={isCollapsed ? 'Expand' : 'Collapse'}
        >
          {isCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>

      {/* New chat */}
      <div className="px-2 py-2.5 border-b border-slate-700/50 shrink-0">
        <button
          onClick={onNewChat}
          className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-700/40 hover:bg-slate-700/70 text-slate-200 text-sm transition-colors ${
            isCollapsed ? 'justify-center' : ''
          }`}
          title="New chat"
        >
          <PlusCircle className="w-4 h-4 shrink-0" />
          {!isCollapsed && <span>New chat</span>}
        </button>
      </div>

      {/* Session list */}
      {!isCollapsed ? (
        <div className="flex-1 overflow-y-auto py-2 px-2 space-y-0.5">
          {sessions.length === 0 && (
            <p className="text-xs text-slate-500 px-3 py-2">No sessions yet</p>
          )}
          {sessions.map(s => (
            <div
              key={s.id}
              className={`group w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs cursor-pointer transition-colors ${
                activeSessionId === s.id
                  ? 'bg-slate-600/60 text-white'
                  : 'text-slate-400 hover:text-white hover:bg-slate-700/40'
              }`}
              onClick={() => onSelectSession(s.id)}
            >
              <MessageSquare className="w-3.5 h-3.5 shrink-0 opacity-60" />
              <span
                className="truncate flex-1 text-left"
                title={s.title || 'Untitled'}
              >{s.title || 'Untitled'}</span>
              <button
                onClick={(e) => deleteSession(e, s.id)}
                className="opacity-0 group-hover:opacity-100 p-0.5 hover:text-red-400 transition-all rounded shrink-0"
                title="Delete session"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      ) : (
        sessions.length > 0 && (
          <div className="flex-1 flex flex-col items-center py-3 gap-1">
            <div className="w-8 h-8 rounded-lg bg-slate-700/40 flex items-center justify-center">
              <MessageSquare className="w-4 h-4 text-slate-400" />
            </div>
            <span className="text-[10px] text-slate-500">{sessions.length}</span>
          </div>
        )
      )}

      {/* Resize handle */}
      {!isCollapsed && (
        <div
          onMouseDown={onMouseDown}
          className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-indigo-500/40 transition-colors"
          style={{ userSelect: 'none' }}
        />
      )}
    </aside>
  )
}
