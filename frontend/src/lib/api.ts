import { API_BASE } from './config'

function buildHeaders(token?: string | null, anonId?: string | null): Record<string, string> {
  const h: Record<string, string> = {}
  if (token)  h['Authorization'] = `Bearer ${token}`
  if (anonId) h['X-Anon-Id'] = anonId
  return h
}

async function get<T>(path: string, token?: string | null, anonId?: string | null): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: buildHeaders(token, anonId) })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

async function post<T>(path: string, body: unknown, token?: string | null, anonId?: string | null): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...buildHeaders(token, anonId) },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

// ── Types ─────────────────────────────────────────────────────────────────

export interface Source {
  id?: string | number
  ticker?: string
  company?: string
  company_name?: string
  source?: string        // '10k' | 'transcript' | 'news'
  chunk_text?: string
  similarity?: number
  marker?: string
  // 10-K fields
  filing_year?: number
  fiscal_year?: number | string
  section?: string
  // transcript fields
  year?: number | string
  quarter?: number | string
  // news
  title?: string
  url?: string
  published_date?: string
}

export interface ReasoningStep {
  step: string
  message: string
  chunks?: Array<{ ticker: string; source: string; text: string; year?: string | number; section?: string }>
  data?: Record<string, unknown>  // v2 structured event payload
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  reasoning?: ReasoningStep[]
  confidence?: number
  isStreaming?: boolean
  timestamp?: Date
}

export type Message = ChatMessage   // legacy alias

export interface Session {
  id: string
  title: string
  created_at: string
  message_count: number
}

export interface Company {
  ticker: string
  company_name: string
  sector?: string
}

// ── WS message shapes ──────────────────────────────────────────────────────

export interface WsAck    { type: 'ack';    session_id: string }
export interface WsStatus {
  type: 'status'
  step: string
  message: string
  chunks?: Array<{ ticker: string; source: string; text: string; year?: string | number; section?: string }>
}
export interface WsAnswer {
  type: 'answer'
  answer: string
  citations: Source[]
  confidence: number
  reasoning: ReasoningStep[]
  session_id: string
}
export interface WsToken     { type: 'token';     token: string }
export interface WsError     { type: 'error';     detail: string }
export interface WsPong      { type: 'pong' }
export interface WsCancelled { type: 'cancelled' }

// v2 structured events
export interface WsPlanComplete {
  type: 'plan_complete'
  axes: { entities: string[]; metrics: string[]; time_refs: unknown[]; intents: string[] }
  sub_questions: Array<{ id: string; text: string; entity: string; metric: string; time_ref_label: string; preferred_source: string }>
  needs_web: boolean
}
export interface WsSubqStart     { type: 'subq_start';      id: string; text: string; entity: string; metric: string; time_ref: string }
export interface WsSubqRetrieved { type: 'subq_retrieved';  id: string; rag_chunks: number }
export interface WsSubqComplete  { type: 'subq_complete';   id: string; no_info: boolean; confidence: number; citation_count: number }
export interface WsGapFillStart  { type: 'gap_fill_start';  ids: string[] }
export interface WsGapFillComplete { type: 'gap_fill_complete'; id: string; recovered: boolean }
export interface WsAggregating   { type: 'aggregating' }
export interface WsValidated     { type: 'validated'; score: number; missing_dimensions: string[]; refusal_appropriate: boolean }

export type WsEvent =
  | WsAck | WsStatus | WsToken | WsAnswer | WsError | WsPong | WsCancelled
  | WsPlanComplete | WsSubqStart | WsSubqRetrieved | WsSubqComplete
  | WsGapFillStart | WsGapFillComplete | WsAggregating | WsValidated

// ── API calls ─────────────────────────────────────────────────────────────

export const listSessions  = (token?: string | null, anonId?: string | null) =>
  get<{ sessions: Session[] }>('/sessions', token, anonId)

export const createSession = (title: string, token?: string | null, anonId?: string | null) =>
  post<{ id: string; title: string }>('/sessions', { title }, token, anonId)

export const getHealth = () =>
  get<{ status: string; db: boolean }>('/health')

export function generateMessageId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}
