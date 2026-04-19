import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

// FIX: VoiceProvider was here AND inside App.tsx — two WebSocket connections
// fighting each other, double TTS calls, broken state. Removed from here.
// App.tsx owns the single VoiceProvider.
ReactDOM.createRoot(document.getElementById('root')!).render(
  <App />
)