import { useState } from 'react'
import { SignIn, SignUp } from '@clerk/clerk-react'
import { X } from 'lucide-react'
import { AUTH_AVAILABLE } from '../lib/config'

const clerkAppearance = {
  variables: {
    colorPrimary: '#6366f1',
    colorBackground: '#0d1f3c',
    colorText: '#e2e8f0',
    colorInputBackground: '#1e293b',
    colorInputText: '#f1f5f9',
    colorTextSecondary: '#94a3b8',
    colorDanger: '#f87171',
    borderRadius: '0.75rem',
    fontFamily: 'Inter, system-ui, sans-serif',
  },
  elements: {
    card: 'bg-transparent shadow-none border-0',
    headerTitle: 'text-white text-lg font-bold',
    headerSubtitle: 'text-slate-400 text-sm',
    formButtonPrimary: 'bg-indigo-600 hover:bg-indigo-700 text-white font-medium',
    footerActionLink: 'text-indigo-400 hover:text-indigo-300',
    formFieldLabel: 'text-slate-300 text-sm',
    dividerLine: 'bg-slate-700',
    dividerText: 'text-slate-500',
    socialButtonsBlockButton: 'border-slate-700 text-slate-300 hover:bg-slate-800',
  },
}

interface Props {
  isOpen: boolean
  onClose: () => void
  defaultTab?: 'sign-in' | 'sign-up'
}

export default function AuthModal({ isOpen, onClose, defaultTab = 'sign-in' }: Props) {
  const [tab, setTab] = useState<'sign-in' | 'sign-up'>(defaultTab)

  // AUTH_AVAILABLE is compile-time constant — safe to bail early
  if (!isOpen || !AUTH_AVAILABLE) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />

      <div className="relative bg-[#0a1628] border border-slate-700/60 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-4 border-b border-slate-700/50">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 bg-indigo-500 rounded-lg flex items-center justify-center text-white text-sm font-black">α</div>
            <div className="flex gap-0.5 bg-slate-800/70 rounded-lg p-1">
              {(['sign-in', 'sign-up'] as const).map(t => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`px-3.5 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    tab === t ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {t === 'sign-in' ? 'Sign In' : 'Sign Up'}
                </button>
              ))}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-white transition-colors p-1 rounded-lg hover:bg-slate-800"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Clerk component */}
        <div className="px-4 py-4">
          {tab === 'sign-in' ? (
            <SignIn routing="hash" afterSignInUrl="/chat" appearance={clerkAppearance} />
          ) : (
            <SignUp routing="hash" afterSignUpUrl="/chat" appearance={clerkAppearance} />
          )}
        </div>
      </div>
    </div>
  )
}
