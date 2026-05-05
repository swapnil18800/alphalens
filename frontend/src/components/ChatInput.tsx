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
      disabled ? 'border-neutral-200' : 'border-neutral-300 focus-within:border-black'
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
          className="flex-1 resize-none bg-transparent text-sm text-neutral-800 placeholder-neutral-400 outline-none leading-relaxed max-h-[168px] overflow-y-auto disabled:cursor-not-allowed"
        />

        {/* Stop button (during inference) */}
        {disabled && onStop ? (
          <button
            onClick={onStop}
            className="flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center bg-neutral-100 hover:bg-black hover:text-white text-neutral-500 transition-colors"
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
                ? 'bg-black hover:bg-neutral-800 text-white'
                : 'bg-neutral-100 text-neutral-400 cursor-not-allowed'
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

      {/* Web search toggle */}
      {onWebSearchToggle && (
        <div className="flex items-center gap-2 mt-2 pt-2 border-t border-neutral-100">
          <button
            onClick={onWebSearchToggle}
            className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg transition-colors font-medium ${
              webSearch
                ? 'bg-black text-white'
                : 'text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100'
            }`}
            title={webSearch ? 'Web search on — click to disable' : 'Enable web search (Tavily)'}
          >
            <Globe className="w-3 h-3" />
            Web
          </button>
        </div>
      )}
    </div>
  )
}
