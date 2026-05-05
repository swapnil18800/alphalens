const ANON_KEY = 'al_anon_id'

function initAnonId(): string {
  try {
    let id = sessionStorage.getItem(ANON_KEY)
    if (!id) {
      id = 'anon_' + crypto.randomUUID()
      sessionStorage.setItem(ANON_KEY, id)
    }
    return id
  } catch {
    return 'anon_' + Math.random().toString(36).slice(2)
  }
}

// Eagerly initialize so the same value is returned throughout the session
const ANON_ID = initAnonId()

export function useAnonId(): string {
  return ANON_ID
}
