import { X } from 'lucide-react'
import { useSignIn } from '@clerk/clerk-react'
import { AUTH_AVAILABLE } from '../lib/config'

interface Props {
  isOpen: boolean
  onClose: () => void
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M17.64 9.2a10.3 10.3 0 0 0-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z" fill="#4285F4"/>
      <path d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.83.86-3.04.86-2.34 0-4.32-1.58-5.03-3.71H.96v2.33A9 9 0 0 0 9 18Z" fill="#34A853"/>
      <path d="M3.97 10.71A5.41 5.41 0 0 1 3.68 9c0-.6.1-1.17.29-1.71V4.96H.96A9 9 0 0 0 0 9c0 1.45.35 2.82.96 4.04l3.01-2.33Z" fill="#FBBC05"/>
      <path d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.96L3.97 7.3C4.68 5.16 6.66 3.58 9 3.58Z" fill="#EA4335"/>
    </svg>
  )
}

function AuthModalInner({ onClose }: { onClose: () => void }) {
  const { signIn } = useSignIn()

  const handleGoogle = async () => {
    if (!signIn) return
    try {
      await signIn.authenticateWithRedirect({
        strategy: 'oauth_google',
        redirectUrl: '/sso-callback',
        redirectUrlComplete: '/chat',
      })
    } catch (e) {
      console.error('[auth] Google OAuth error', e)
    }
  }

  return (
    <div className="px-8 pt-8 pb-7 flex flex-col items-center text-center">
      <div className="flex items-center gap-2.5 mb-5">
        <div className="w-8 h-8 bg-black rounded-lg flex items-center justify-center text-white font-black text-base shrink-0">α</div>
        <span className="font-bold text-black text-base">AlphaLens</span>
      </div>
      <h3 className="text-xl font-bold text-black mb-1">Sign in</h3>
      <p className="text-sm text-neutral-500 mb-6 leading-snug">Save your research sessions across devices.</p>

      <button
        onClick={handleGoogle}
        className="w-full flex items-center justify-center gap-3 border border-black/12 rounded-xl py-3 px-4 hover:bg-neutral-50 hover:border-black/25 transition-all font-medium text-sm text-black"
      >
        <GoogleIcon />
        Continue with Google
      </button>

      <p className="text-[10px] text-neutral-400 mt-5 leading-relaxed">
        Research use only — AlphaLens does not provide investment advice.
      </p>
    </div>
  )
}

export default function AuthModal({ isOpen, onClose }: Props) {
  if (!isOpen || !AUTH_AVAILABLE) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-sm border border-black/8 overflow-hidden">
        <button
          onClick={onClose}
          className="absolute top-3.5 right-3.5 text-neutral-400 hover:text-black transition-colors p-1 rounded-lg hover:bg-neutral-100 z-10"
        >
          <X className="w-4 h-4" />
        </button>
        <AuthModalInner onClose={onClose} />
      </div>
    </div>
  )
}
