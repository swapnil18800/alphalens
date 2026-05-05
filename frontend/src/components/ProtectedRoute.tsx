import { useAuth, SignIn } from '@clerk/clerk-react'

interface Props {
  children: React.ReactNode
}

/**
 * Wraps a route to require Clerk authentication.
 * - Loading: shows spinner on dark background
 * - Not signed in: renders Clerk's <SignIn /> UI centred on page
 * - Signed in: renders children
 */
export default function ProtectedRoute({ children }: Props) {
  const { isLoaded, isSignedIn } = useAuth()

  if (!isLoaded) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#0a1628]">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
      </div>
    )
  }

  if (!isSignedIn) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#0a1628]">
        <SignIn
          routing="hash"
          afterSignInUrl="/chat"
          afterSignUpUrl="/chat"
          appearance={{
            variables: {
              colorPrimary: '#6366f1',
              colorBackground: '#0f172a',
              colorText: '#e2e8f0',
              colorInputBackground: '#1e293b',
              colorInputText: '#f1f5f9',
            },
          }}
        />
      </div>
    )
  }

  return <>{children}</>
}
