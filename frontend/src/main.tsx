import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ClerkProvider } from '@clerk/clerk-react'
import App from './App'
import './index.css'
import { AUTH_DISABLED } from './lib/config'

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

function Root() {
  if (AUTH_DISABLED || !PUBLISHABLE_KEY) {
    return (
      <BrowserRouter>
        <App />
      </BrowserRouter>
    )
  }
  return (
    <ClerkProvider publishableKey={PUBLISHABLE_KEY}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ClerkProvider>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(<Root />)
