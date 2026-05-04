export const API_BASE = ''   // empty = same origin (Vite proxy in dev, FastAPI in prod)
export const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`
export const AUTH_DISABLED = import.meta.env.VITE_AUTH_DISABLED === 'true'
