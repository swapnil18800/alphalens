import { useState, useRef, type KeyboardEvent } from 'react'
import { ArrowUp, Loader2, Square, Globe } from 'lucide-react'

interface Props {
  onSend: (text: string) => void
  onStop?: () => void
  disabled?: boolean
  placeholder?: string
  autoFocus?: boolean
  webSearch?: boolean
  onWebSearchToggle?: () => void
}

export default function ChatInput({
  onSend,
  onStop,
  disabled = false,
  placeholder = 'Ask about any company…',
  autoFocus = true,
  webSearch = false,
  onWebSearchToggle,
}: Props) {
  const [value, setValue] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)

  const submit = () => {
    const text = value.trim()
    if (!text || disabled) return
    onSend(text)
    setValue('')
    if (ref.current) ref.current.style.height = 'auto'
  }

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const onInput = () => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`
  }

  const canSend = value.trim().length > 0 && !disabled

  return (
    <div className={`bg-white border rounded-2xl px-4 py-3 shadow-sm transition-colors ${
      disabled ? 'border-slate-200' : 'border-slate-300 focus-within:border-[#0a1628]'
    }`}>
      <div className="flex items-end gap-3">
        <textarea
          ref={ref}
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={onKey}
          onInput={onInput}
          rows={1}
          disabled={disabled}
          placeholder={placeholder}
          autoFocus={autoFocus}
          className="flex-1 resize-none bg-transparent text-sm text-slate-800 placeholder-slate-400 outline-none leading-relaxed max-h-[168px] overflow-y-auto disabled:cursor-not-allowed"
        />

        {/* Stop button (during inference) */}
        {disabled && onStop ? (
          <button
            onClick={onStop}
            className="flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center bg-slate-100 hover:bg-slate-200 text-slate-500 transition-colors"
            aria-label="Stop generation"
            title="Stop"
          >
            <Square className="w-3.5 h-3.5 fill-current" />
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!canSend}
            className={`flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center transition-colors ${
              canSend
                ? 'bg-[#0a1628] hover:bg-slate-700 text-white'
                : 'bg-slate-100 text-slate-400 cursor-not-allowed'
            }`}
            aria-label="Send"
          >
            {disabled
              ? <Loader2 className="w-4 h-4 animate-spin" />
              : <ArrowUp  className="w-4 h-4" />
            }
          </button>
        )}
      </div>

      {/* Web search toggle row */}
      {onWebSearchToggle && (
        <div className="flex items-center gap-2 mt-2 pt-2 border-t border-slate-100">
          <button
            onClick={onWebSearchToggle}
            className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded-lg transition-colors ${
              webSearch
                ? 'bg-blue-50 text-blue-600 border border-blue-200'
                : 'text-slate-400 hover:text-slate-600 hover:bg-slate-50'
            }`}
            title={webSearch ? 'Web search on — click to disable' : 'Enable web search (Tavily)'}
          >
            <Globe className="w-3 h-3" />
            Web search
            {webSearch && <span className="w-1.5 h-1.5 bg-blue-500 rounded-full" />}
          </button>
        </div>
      )}
    </div>
  )
}
