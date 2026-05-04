import { useAuth } from '@clerk/clerk-react'
import { AUTH_DISABLED } from '../lib/config'

export function useAuthStatus() {
  if (AUTH_DISABLED) {
    return { isSignedIn: true, token: null, isLoaded: true }
  }
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const { isSignedIn, getToken, isLoaded } = useAuth()
  const getAuthToken = async () => (isSignedIn ? getToken() : null)
  return { isSignedIn: isSignedIn ?? false, getToken: getAuthToken, isLoaded }
}
