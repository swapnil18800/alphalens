import { Routes, Route, Navigate } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import ChatPage from './pages/ChatPage'

export default function App() {
  return (
    <Routes>
      <Route path="/"     element={<LandingPage />} />
      <Route path="/chat" element={<ChatPage />} />
      <Route path="*"     element={<Navigate to="/" replace />} />
    </Routes>
  )
}
