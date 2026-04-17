import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import { ConversationProvider } from '@elevenlabs/react'
import { VoiceProvider } from './contexts/VoiceContext'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConversationProvider>
      <VoiceProvider>
        <App />
      </VoiceProvider>
    </ConversationProvider>
  </React.StrictMode>,
)
