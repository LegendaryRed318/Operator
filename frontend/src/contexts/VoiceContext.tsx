import React, { createContext, useContext, useState, useCallback, useRef, ReactNode, useEffect } from 'react';
import { getWebSocketUrl } from '../utils/urls';

export type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'offline' | 'hotword';

interface VoiceContextType {
  state: VoiceState;
  isOffline: boolean;
  lastResponse: string;
  interimText: string;
  manualWake: () => Promise<void>;
  sendTextCommand: (text: string) => Promise<void>;
  messages: any[];
  wsConnected: boolean;
  isConversationMode: boolean;
  toggleConversationMode: () => void;
  audioLevel: number; // 0-1 for orb visualization
}

const VoiceContext = createContext<VoiceContextType | undefined>(undefined);

interface VoiceProviderProps {
  children: ReactNode;
}

const FOLLOW_UP_WINDOW_MS = 20 * 1000; // 20 second conversation follow-up window
const VOICE_SERVICE_URL = 'ws://localhost:8766'; // Local Whisper voice service

/**
 * Clean markdown/formatting from text before speaking.
 * pyttsx3 reads asterisks and pound signs aloud — this prevents that.
 */
function cleanTextForSpeech(text: string): string {
  return text
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/#{1,6}\s/g, '')
    .replace(/`{1,3}(.*?)`{1,3}/gs, '$1')
    .replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1')
    .replace(/[-*+]\s/g, '')
    .replace(/\n{2,}/g, '. ')
    .replace(/\n/g, ' ')
    .trim();
}

export const VoiceProvider: React.FC<VoiceProviderProps> = ({ children }) => {
  const [state, setState] = useState<VoiceState>('idle');
  const [isOffline, setIsOffline] = useState(false);
  const [lastResponse, setLastResponse] = useState('');
  const [messages, setMessages] = useState<any[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [interimText, setInterimText] = useState('');
  const [isConversationMode, setIsConversationMode] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0); // 0-1 for orb visualization

  // Main JARVIS WebSocket (port 8765)
  const ws = useRef<WebSocket | null>(null);
  // Voice Service WebSocket (port 8766 - local Whisper)
  const voiceWs = useRef<WebSocket | null>(null);
  
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 3;
  const reconnectDelay = 5000;
  
  const isSpeakingRef = useRef(false);
  const isConnecting = useRef(false);
  const isVoiceServiceConnecting = useRef(false);

  const ttsDurationTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const followUpTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const speakCooldown = useRef<boolean>(false);
  
  const stateWatchdogRef = useRef<{ state: VoiceState; since: number }>({ state: 'idle', since: Date.now() });

  // Use a ref for isConversationMode so callbacks get latest value without dependencies
  const isConversationModeRef = useRef(isConversationMode);
  useEffect(() => {
    isConversationModeRef.current = isConversationMode;
  }, [isConversationMode]);

  const setVoiceState = useCallback((newState: VoiceState, offline = false) => {
    setState(newState);
    setIsOffline(offline);
    stateWatchdogRef.current = { state: newState, since: Date.now() };
  }, []);

  const toggleConversationMode = useCallback(() => {
    setIsConversationMode(prev => {
      const next = !prev;
      console.log(`[Voice] Conversation mode: ${next ? 'ON' : 'OFF'}`);
      return next;
    });
  }, []);

  // Orb state watchdog
  useEffect(() => {
    const watchdog = setInterval(() => {
      const { state: trackedState, since } = stateWatchdogRef.current;
      const elapsed = Date.now() - since;
      
      if (trackedState === 'thinking' && elapsed > 15000) {
        console.warn('[Watchdog] Stuck in thinking state for >15s. Forcing reset.');
        setVoiceState('idle');
      } else if (trackedState === 'speaking' && elapsed > 20000 && !isSpeakingRef.current) {
        console.warn('[Watchdog] Stuck in speaking state for >20s. Forcing reset.');
        setVoiceState('idle');
      }
    }, 5000);
    return () => clearInterval(watchdog);
  }, [setVoiceState]);

  const onSpeechFinished = useCallback(() => {
    isSpeakingRef.current = false;
    if (ttsDurationTimeout.current) {
      clearTimeout(ttsDurationTimeout.current);
      ttsDurationTimeout.current = null;
    }

    if (isConversationModeRef.current) {
      console.log('[Voice] Conversation mode ON — Starting follow-up window (20s) — auto-listening enabled');
      
      // Reset the follow-up timer
      if (followUpTimeoutRef.current) clearTimeout(followUpTimeoutRef.current);

      followUpTimeoutRef.current = setTimeout(() => {
        console.log('[Voice] Follow-up window expired — returning to idle');
        followUpTimeoutRef.current = null;
        setVoiceState('idle');
      }, FOLLOW_UP_WINDOW_MS);
    } else {
      // Give a small cooldown before transitioning state
      setTimeout(() => {
        setVoiceState('idle');
      }, 900);
    }
  }, [setVoiceState]);

  // Initialize Voice Service WebSocket (Whisper local ASR)
  const initVoiceService = useCallback(async (): Promise<boolean> => {
    return new Promise((resolve) => {
      if (voiceWs.current?.readyState === WebSocket.OPEN) {
        resolve(true);
        return;
      }
      if (voiceWs.current?.readyState === WebSocket.CONNECTING || isVoiceServiceConnecting.current) {
        resolve(false);
        return;
      }

      isVoiceServiceConnecting.current = true;
      console.log('[Voice] Connecting to Voice Service (Whisper)...');
      
      voiceWs.current = new WebSocket(VOICE_SERVICE_URL);
      let connected = false;

      voiceWs.current.onopen = () => {
        isVoiceServiceConnecting.current = false;
        console.log('[Voice] Connected to Voice Service');
        connected = true;
        resolve(true);
      };

      voiceWs.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'connected') {
            console.log('[Voice] Voice Service:', data.message);
          } else if (data.type === 'vad_start') {
            // Speech detected, orb shows LISTENING
            if (state === 'idle') {
              setVoiceState('listening');
            }
          } else if (data.type === 'audio_level') {
            // Real-time audio amplitude for orb visualization
            setAudioLevel(data.level || 0);
          } else if (data.type === 'vad_end') {
            // Speech ended, will get transcript shortly
          } else if (data.type === 'transcript') {
            // Regular transcript (no wake word) - display as subtitle only
            setInterimText(data.transcript);
            setTimeout(() => setInterimText(''), 3000);
          } else if (data.type === 'wake_word') {
            // Wake word detected!
            console.log('[Voice] Wake word detected:', data.wake_word, 'intent:', data.intent);
            setInterimText(data.transcript);

            // Send command to main JARVIS with intent for routing
            if (ws.current?.readyState === WebSocket.OPEN) {
              setVoiceState('thinking');
              ws.current.send(JSON.stringify({
                type: 'voice_command',
                text: data.transcript,
                intent: data.intent || 'conversation'
              }));
            }
          }
        } catch (e) {
          console.error('[Voice] Failed to parse voice service message:', e);
        }
      };

      voiceWs.current.onerror = (err) => {
        console.error('[Voice] Voice Service WebSocket error:', err);
      };

      voiceWs.current.onclose = () => {
        isVoiceServiceConnecting.current = false;
        if (!connected) {
          resolve(false);
        }
        // Auto-reconnect after 5 seconds
        setTimeout(() => initVoiceService(), 5000);
      };

      setTimeout(() => {
        if (!connected && voiceWs.current?.readyState !== WebSocket.OPEN) {
          voiceWs.current?.close();
        }
      }, 3000);
    });
  }, [state, setVoiceState, setInterimText]);

  // Initialize Main JARVIS WebSocket (port 8765)
  const initWebSocket = useCallback(async (): Promise<boolean> => {
    return new Promise((resolve) => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        resolve(true);
        return;
      }
      if (ws.current?.readyState === WebSocket.CONNECTING || isConnecting.current) {
        resolve(false);
        return;
      }

      isConnecting.current = true;
      if (isOffline) {
        setIsOffline(false);
        reconnectAttempts.current = 0;
      }

      const wsUrl = getWebSocketUrl();
      ws.current = new WebSocket(wsUrl);
      let connected = false;

      ws.current.onopen = () => {
        isConnecting.current = false;
        console.log(`[Voice] Connected to JARVIS at ${wsUrl}`);
        reconnectAttempts.current = 0;
        setIsOffline(false);
        connected = true;
        setWsConnected(true);
        resolve(true);
      };

      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setMessages(prev => [...prev.slice(-49), data]);

          if (data.type === 'response') {
            const responseText = data.text || "I'm sorry sir, I didn't catch that.";
            setLastResponse(responseText);
            setVoiceState('speaking');

            if (data.server_tts) {
              console.log(`[Voice] Server TTS active — waiting for tts_done event`);
              isSpeakingRef.current = true;

              if (ttsDurationTimeout.current) clearTimeout(ttsDurationTimeout.current);

              ttsDurationTimeout.current = setTimeout(() => {
                console.warn('[Voice] tts_done never arrived — recovering after safety timeout (12s)');
                onSpeechFinished();
              }, 12000);

            } else {
              const cleanText = cleanTextForSpeech(responseText);
              speak(cleanText, onSpeechFinished);
            }

          } else if (data.type === 'tts_done') {
            console.log('[Voice] Server TTS finished (tts_done received) — resetting state');
            if (ttsDurationTimeout.current) clearTimeout(ttsDurationTimeout.current);
            isSpeakingRef.current = false;
            onSpeechFinished();
          } else if (data.type === 'tts_fallback') {
            console.log(`[Voice] Server TTS failed (${data.reason}) — using browser fallback`);
            if (ttsDurationTimeout.current) clearTimeout(ttsDurationTimeout.current);
            const fallbackText = data.text || "I'm sorry sir, I didn't catch that.";
            const cleanText = cleanTextForSpeech(fallbackText);
            setVoiceState('speaking');
            speak(cleanText, onSpeechFinished);
          } else if (data.type === 'state') {
            if (data.state === 'thinking') setVoiceState('thinking');
          } else if (data.type === 'ack') {
            console.log('[Voice]', data.message);
          }
        } catch (e) {
          console.error('[Voice] Failed to parse message:', e);
        }
      };

      ws.current.onerror = (err) => {
        console.error('[Voice] WebSocket error:', err);
      };

      ws.current.onclose = () => {
        isConnecting.current = false;
        reconnectAttempts.current++;
        setWsConnected(false);
        if (reconnectAttempts.current >= maxReconnectAttempts) {
          setIsOffline(true);
          setVoiceState('idle', true);
          resolve(false);
          return;
        }
        if (!connected && !isOffline) {
          setTimeout(() => initWebSocket().then(resolve), reconnectDelay);
        }
      };

      setTimeout(() => {
        if (!connected && ws.current?.readyState !== WebSocket.OPEN) {
          ws.current?.close();
        }
      }, 3000);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOffline, setVoiceState, onSpeechFinished]);

  // Browser TTS fallback (when server TTS fails)
  const speakWithBrowserTTS = useCallback((text: string, onDone?: () => void) => {
    if (!text.trim()) {
      onDone?.();
      return;
    }

    console.log(`[TTS] Browser speaking: ${text.substring(0, 60)}...`);
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.88;
    utterance.pitch = 0.92;
    utterance.volume = 1.0;

    const trySpeak = () => {
      const voices = window.speechSynthesis.getVoices();
      if (voices.length === 0) {
        setTimeout(trySpeak, 100);
        return;
      }

      const britishMale = voices.find(v =>
        (v.name.includes('George') || v.name.includes('David') || v.name.includes('James')) &&
        v.lang.startsWith('en')
      );
      const enGB = voices.find(v => v.lang === 'en-GB');
      const anyEnglish = voices.find(v => v.lang.startsWith('en'));

      const chosen = britishMale || enGB || anyEnglish;
      if (chosen) {
        utterance.voice = chosen;
        console.log(`[TTS] Using voice: ${chosen.name} (${chosen.lang})`);
      }

      utterance.onend = () => {
        console.log('[TTS] Browser speech finished');
        onDone?.();
      };

      utterance.onerror = (e) => {
        if (e.error !== 'interrupted') {
          console.error('[TTS] Browser speech error:', e.error);
        }
        onDone?.();
      };

      window.speechSynthesis.speak(utterance);
    };

    trySpeak();
  }, []);

  const speak = useCallback((text: string, onDone?: () => void) => {
    isSpeakingRef.current = true;
    speakCooldown.current = true;
    speakWithBrowserTTS(text, () => {
      isSpeakingRef.current = false;
      speakCooldown.current = false;
      onDone?.();
    });
  }, [speakWithBrowserTTS]);

  // Manual wake - immediately start listening (for button clicks)
  const manualWake = useCallback(async () => {
    setVoiceState('listening');
  }, [setVoiceState]);

  // Send text command directly to JARVIS
  const sendTextCommand = useCallback(async (text: string) => {
    if (!text.trim()) return;
    const connected = await initWebSocket();
    if (!connected) {
      console.error('[Voice] Cannot send text — WebSocket not connected');
      return;
    }
    setVoiceState('thinking');
    ws.current?.send(JSON.stringify({ type: 'command', text: text.trim() }));
    console.log('[Voice] Text command sent:', text);
  }, [initWebSocket, setVoiceState]);

  // Initialize both WebSockets on mount
  useEffect(() => {
    initWebSocket();
    initVoiceService();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <VoiceContext.Provider value={{
      state,
      isOffline,
      lastResponse,
      interimText,
      manualWake,
      sendTextCommand,
      messages,
      wsConnected,
      isConversationMode,
      toggleConversationMode,
      audioLevel
    }}>
      {children}
    </VoiceContext.Provider>
  );
};

export const useVoice = (): VoiceContextType => {
  const context = useContext(VoiceContext);
  if (context === undefined) {
    throw new Error('useVoice must be used within a VoiceProvider');
  }
  return context;
};

export default VoiceContext;