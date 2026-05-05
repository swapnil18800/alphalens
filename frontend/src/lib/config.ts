export const API_BASE = ''   // empty = same origin (Vite proxy in dev, FastAPI in prod)
export const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`
export const AUTH_DISABLED = import.meta.env.VITE_AUTH_DISABLED === 'true'
// Auth is available when Clerk publishable key is set and auth is not explicitly disabled
export const AUTH_AVAILABLE = !AUTH_DISABLED && !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY
