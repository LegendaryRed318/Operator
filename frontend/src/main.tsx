import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import { VoiceProvider } from './contexts/VoiceContext'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <VoiceProvider>
      <App />
    </VoiceProvider>
  </React.StrictMode>,
)
