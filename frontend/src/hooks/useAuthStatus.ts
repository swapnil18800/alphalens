import { useAuth, useUser, useClerk } from '@clerk/clerk-react'
import { AUTH_AVAILABLE } from '../lib/config'

export interface AuthUser {
  firstName?: string | null
  lastName?: string | null
  fullName?: string | null
  username?: string | null
  imageUrl?: string
  emailAddresses?: { emailAddress: string }[]
}

export interface AuthStatus {
  isSignedIn: boolean
  getToken: () => Promise<string | null>
  isLoaded: boolean
  user: AuthUser | null
  signOut: () => Promise<void>
}

export function useAuthStatus(): AuthStatus {
  if (!AUTH_AVAILABLE) {
    // Hooks deliberately NOT called here (AUTH_AVAILABLE is a compile-time constant)
    return {
      isSignedIn: false,
      getToken: async () => null,
      isLoaded: true,
      user: null,
      signOut: async () => {},
    }
  }
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const { isSignedIn, getToken, isLoaded } = useAuth()
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const { user } = useUser()
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const { signOut } = useClerk()
  return {
    isSignedIn: isSignedIn ?? false,
    getToken: async () => (isSignedIn ? getToken() : null),
    isLoaded: isLoaded ?? false,
    user: user ?? null,
    signOut: () => signOut(),
  }
}
