# Frontend

## Stack

React 18 + Vite + TypeScript + Tailwind CSS + framer-motion. No state management library — uses React hooks only.

## Dev server

```bash
cd frontend && npm run dev   # port 5175
```

Vite proxies API calls to `localhost:8000` (configured in `vite.config.ts`).

## Pages

| Page | File | Route |
|------|------|-------|
| Landing | `pages/LandingPage.tsx` | `/` |
| Chat (main) | `pages/ChatPage.tsx` | `/chat` |
| Companies | `pages/CompaniesPage.tsx` | `/companies` |
| Screener | `pages/ScreenerPage.tsx` | `/screener` |

## Key Components

| Component | File | Purpose |
|-----------|------|---------|
| `ChatInput` | `components/ChatInput.tsx` | Message input with web search toggle and stop button |
| `ChatMessage` | `components/ChatMessage.tsx` | Renders message + citations panel + confidence |
| `ReasoningTrace` | `components/ReasoningTrace.tsx` | Expandable reasoning steps with inline chunk cards |
| `Sidebar` | `components/Sidebar.tsx` | Session list, drag-to-resize, new chat, delete session |
| `AboutModal` | `components/AboutModal.tsx` | About dialog |

## WebSocket integration (ChatPage.tsx)

- Single `useCallback` with `[]` deps for stable WS `connect` function
- `sessionIdRef` mirrors `sessionId` state — used inside WS handlers to avoid stale closures
- `assistantId.current` tracks which message receives streaming tokens
- Token accumulation: `{type: "token"}` → append to `message.content`
- `{type: "answer"}` replaces accumulated content with final answer (includes full citations)

## Design system

- Color: Minimalist slate palette, `bg-[#faf9f7]` background, `#0a1628` dark accents
- Typography: Inter (body) + Playfair Display (serif headings), base 17px
- Icons: lucide-react
- Animations: framer-motion for page transitions
- Layout: Fixed sidebar (drag-resizable 160-360px) + scrollable main area

## Types (api.ts)

- `ChatMessage`: id, role, content, sources, reasoning, confidence, isStreaming
- `Source`: ticker, source type, chunk_text, similarity, filing_year, section, etc.
- `ReasoningStep`: step name, message, optional chunk previews
- `WsEvent`: union of all server→client message types
