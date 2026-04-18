import React, { createContext, useContext, useState, useCallback, useRef, ReactNode, useEffect } from 'react';

export type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'offline' | 'hotword';

interface VoiceContextType {
  state: VoiceState;
  isOffline: boolean;
  lastResponse: string;
  interimText: string;
  startListening: () => Promise<void>;
  stopListening: () => void;
  manualWake: () => Promise<void>;
  activateHotwordMode: () => void;
  sendTextCommand: (text: string) => Promise<void>;
  messages: any[];
  wsConnected: boolean;
}

const VoiceContext = createContext<VoiceContextType | undefined>(undefined);

interface VoiceProviderProps {
  children: ReactNode;
}

const HOTWORD_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes
const WAKE_WORDS = ['jarvis', 'operator'];
// Common misheard variations of wake words (fuzzy matching)
const WAKE_WORD_FUZZY = ['jarvis', 'operator', 'davas', 'gervais', 'service', 'gervas', 'jarvas', 'jervis'];

// Dynamic WebSocket URL: supports local development and ngrok remote access
// - Local: ws://localhost:8765
// - Ngrok: wss://*.ngrok-free.app (secure WebSocket for remote access)
function getWebSocketUrl(): string {
  const host = window.location.host;
  
  // Check if accessed via ngrok
  if (host.includes('.ngrok-free.app')) {
    // Use secure WebSocket with same ngrok host
    return `wss://${host}/ws`;
  }
  
  // Local development fallback
  return 'ws://localhost:8765';
}

export const VoiceProvider: React.FC<VoiceProviderProps> = ({ children }) => {
  const [state, setState] = useState<VoiceState>('idle');
  const [isOffline, setIsOffline] = useState(false);
  const [lastResponse, setLastResponse] = useState('');
  const [messages, setMessages] = useState<any[]>([]);
  const [wsConnected, setWsConnected] = useState(false);

  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const audioChunks = useRef<Blob[]>([]);
  const ws = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 3;
  const reconnectDelay = 5000;
  const isRecording = useRef(false);

  // Hotword refs
  const hotwordRecognition = useRef<any>(null);
  const hotwordActive = useRef(false);
  const hotwordTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const networkFallbackLogged = useRef(false);
  const hasLoggedNoNetwork = useRef(false);
  
  // Wave gesture debounce (2 seconds)
  const lastWaveTime = useRef(0);
  const WAVE_DEBOUNCE_MS = 2000;
  
  // Voice feedback loop prevention
  const isSpeakingRef = useRef(false);
  const speakCooldown = useRef(false);
  
  // WebSocket initialization guard
  const isConnecting = useRef(false);

  // (Removed ElevenLabs mapped state logic)

  const setVoiceState = useCallback((newState: VoiceState, offline = false) => {
    setState(newState);
    setIsOffline(offline);
  }, []);

  const initWebSocket = useCallback(async (): Promise<boolean> => {
    return new Promise((resolve) => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        resolve(true);
        return;
      }
      if (ws.current?.readyState === WebSocket.CONNECTING || isConnecting.current) {
        resolve(false); // Already connecting, wait
        return;
      }
      
      isConnecting.current = true;

      if (isOffline) {
        setIsOffline(false);
        reconnectAttempts.current = 0;
      }

      const wsUrl = getWebSocketUrl();
      const isRemote = wsUrl.startsWith('wss://');
      
      ws.current = new WebSocket(wsUrl);
      let connected = false;

      ws.current.onopen = () => {
        isConnecting.current = false;
        // Log connection type for debugging
        if (isRemote) {
          console.log('[Voice] Connected to JARVIS via remote ngrok (wss)');
        } else {
          console.log('[Voice] Connected to JARVIS locally (ws)');
        }
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
            setLastResponse(data.text);
            setVoiceState('speaking');
            
            const responseText = data.text || "I'm sorry sir, I didn't catch that.";
            
            // If server is handling TTS, don't speak in browser
            if (data.server_tts) {
              console.log('[Voice] Server handling TTS, skipping browser speech');
              // Wait for server TTS to finish (approximate) then go back to listening
              setTimeout(() => {
                if (hotwordActive.current) {
                  setVoiceState('hotword');
                  hotwordListenLoop();
                } else {
                  setVoiceState('idle');
                }
              }, 2000);
            } else {
              // Browser TTS fallback
              speak(responseText, () => {
                if (hotwordActive.current) {
                  setVoiceState('hotword');
                  hotwordListenLoop();
                } else {
                  setVoiceState('idle');
                }
              });
            }
          } else if (data.type === 'tts_fallback') {
            // Server TTS failed - use browser TTS as fallback
            console.log('[Voice] Server TTS failed, using browser fallback:', data.reason);
            const fallbackText = data.text || "I'm sorry sir, I didn't catch that.";
            speak(fallbackText, () => {
              if (hotwordActive.current) {
                setVoiceState('hotword');
                hotwordListenLoop();
              } else {
                setVoiceState('idle');
              }
            });
          } else if (data.type === 'state') {
            // Only set thinking state from backend, don't override hotword
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
  }, [isOffline, setVoiceState]);

  // Browser TTS fallback - British male voice like JARVIS
  const speakWithBrowserTTS = useCallback((text: string, onDone?: () => void) => {
    // Strip markdown for cleaner speech
    const cleanText = text
      .replace(/\*\*(.*?)\*\*/g, '$1')           // **bold** → bold
      .replace(/\*(.*?)\*/g, '$1')               // *italic* → italic
      .replace(/#{1,6}\s/g, '')                  // ### headers → remove
      .replace(/`{1,3}(.*?)`{1,3}/gs, '$1')     // `code` → code
      .replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1')  // [link](url) → link
      .replace(/[-*+]\s/g, '')                  // - bullet → remove
      .trim();
    
    console.log('🗣️ Speaking with browser TTS:', cleanText.substring(0, 60) + (cleanText.length > 60 ? '...' : ''));
    
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = 0.85;
    utterance.pitch = 0.9;
    utterance.volume = 1.0;
    
    // Try to find British male voice (preferred order)
    const voices = window.speechSynthesis.getVoices();
    const preferred = ['Microsoft David', 'Google UK English Male', 'Daniel', 'en-GB'];
    const britishMale = voices.find(v => 
      preferred.some(p => v.name.includes(p) || v.lang === 'en-GB') && !v.name.includes('Female')
    );
    if (britishMale) {
      utterance.voice = britishMale;
      console.log('[Voice] Using voice:', britishMale.name);
    } else {
      // Fallback to any English voice
      const englishVoice = voices.find(v => v.lang.startsWith('en'));
      if (englishVoice) utterance.voice = englishVoice;
    }
    
    utterance.onend = () => {
      console.log('[Voice] Browser TTS finished');
      onDone?.();
    };
    
    utterance.onerror = (e) => {
      console.error('[Voice] Browser TTS error:', e);
      onDone?.();
    };
    
    window.speechSynthesis.speak(utterance);
  }, []);

  const speak = useCallback((text: string, onDone?: () => void) => {
    isSpeakingRef.current = true;
    speakCooldown.current = true;
    speakWithBrowserTTS(text, () => {
      isSpeakingRef.current = false;
      // 3 second cooldown before hotword can trigger again
      setTimeout(() => { 
        speakCooldown.current = false; 
        onDone?.();
      }, 3000);
    });
  }, [speakWithBrowserTTS]);

  const sendAudioForTranscription = useCallback(async (stream?: MediaStream) => {
    try {
      const audioBlob = new Blob(audioChunks.current, { type: 'audio/webm' });
      if (audioBlob.size === 0) {
        // Stop mic tracks so the browser's orange indicator clears
        stream?.getTracks().forEach(t => t.stop());
        setVoiceState(hotwordActive.current ? 'hotword' : 'idle');
        return;
      }

      const formData = new FormData();
      formData.append('audio', audioBlob, 'recording.webm');

      const response = await fetch('http://localhost:5050/transcribe', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log('[Voice] Transcription received:', data.text);

      // Stop command — expanded stop words
      const lower = data.text.toLowerCase().trim();
      const stopWords = ['stop', 'shut up', 'be quiet', 'silence', 'stop talking', 'shut it', 'quiet', 'enough'];
      if (stopWords.some(w => lower.includes(w))) {
        console.log('[Voice] Stop command received:', lower);
        window.speechSynthesis.cancel();
        isSpeakingRef.current = false;
        speakCooldown.current = false;
        hotwordActive.current = false;
        if (hotwordTimeout.current) clearTimeout(hotwordTimeout.current);
        setVoiceState('idle');
        return;
      }

      if (data.text && data.text.trim()) {
        ws.current?.send(JSON.stringify({ type: 'voice_command', text: data.text }));
      } else {
        setVoiceState(hotwordActive.current ? 'hotword' : 'idle');
        if (hotwordActive.current) hotwordListenLoop();
      }
    } catch (error) {
      console.error('[Voice] Transcription error:', error);
      setVoiceState(hotwordActive.current ? 'hotword' : 'idle');
      if (hotwordActive.current) hotwordListenLoop();
    }
    audioChunks.current = [];
  }, [setVoiceState]);

  const startListening = useCallback(async () => {
    if (isRecording.current || isSpeakingRef.current) return;

    const connected = await initWebSocket();
    if (!connected) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder.current = new MediaRecorder(stream);
      audioChunks.current = [];

      mediaRecorder.current.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunks.current.push(event.data);
      };

      mediaRecorder.current.onstop = async () => {
        isRecording.current = false;
        setVoiceState('thinking');
        stream.getTracks().forEach(track => track.stop());
        await sendAudioForTranscription(stream);
      };

      mediaRecorder.current.start();
      isRecording.current = true;
      setVoiceState('listening');
      console.log('[Voice] Recording started (5 seconds)');

      setTimeout(() => {
        if (mediaRecorder.current && isRecording.current) {
          mediaRecorder.current.stop();
        }
      }, 5000);

    } catch (err) {
      console.error('[Voice] Failed to start recording:', err);
      setVoiceState('idle');
    }
  }, [initWebSocket, sendAudioForTranscription, setVoiceState]);

  // Fallback local hotword loop (Python-based)
  const pythonHotwordLoop = useCallback(async () => {
    if (!hotwordActive.current || isRecording.current || isSpeakingRef.current || speakCooldown.current) return;

    try {
      const connected = await initWebSocket();
      if (!connected) return;

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks: Blob[] = [];

      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
      recorder.onstop = async () => {
        isRecording.current = false;
        stream.getTracks().forEach(t => t.stop());

        const blob = new Blob(chunks, { type: 'audio/webm' });
        if (blob.size < 1000) {
          if (hotwordActive.current) setTimeout(() => pythonHotwordLoop(), 300);
          return;
        }

        try {
          const formData = new FormData();
          formData.append('audio', blob, 'hotword.webm');
          const res = await fetch('http://localhost:5050/transcribe', { method: 'POST', body: formData });
          const data = await res.json();
          const transcript = (data.text || '').toLowerCase().trim();
          console.log('[Hotword-Python] Heard:', transcript);

          // Check for wake words using fuzzy matching
          const wakeDetected = WAKE_WORD_FUZZY.some(w => transcript.includes(w));
          if (wakeDetected && hotwordActive.current) {
            console.log('[Hotword] Wake word detected in:', transcript);
            setVoiceState('listening');
            await startListening();
          } else {
            if (hotwordActive.current) setTimeout(() => pythonHotwordLoop(), 300);
          }
        } catch {
          if (hotwordActive.current) setTimeout(() => pythonHotwordLoop(), 1000);
        }
      };

      recorder.start();
      isRecording.current = true;
      setTimeout(() => { if (recorder.state === 'recording') recorder.stop(); }, 3000);
    } catch (err) {
      console.error('[Hotword-Python] Loop error:', err);
      if (hotwordActive.current) setTimeout(() => pythonHotwordLoop(), 2000);
    }
  }, [initWebSocket, setVoiceState, startListening]);

  // Track interim speech results for visual feedback
  const [interimText, setInterimText] = useState('');

  // Fast browser-based hotword loop
  const hotwordListenLoop = useCallback(() => {
    if (!hotwordActive.current || isRecording.current || isSpeakingRef.current || speakCooldown.current) return;

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn('[Hotword] SpeechRecognition not available, using fallback');
      pythonHotwordLoop();
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;      // short burst, not continuous
    recognition.interimResults = true;     // SHOW what we're hearing in real-time
    recognition.lang = 'en-GB';
    recognition.maxAlternatives = 3;     // Get multiple interpretations for better matching

    let finalTranscript = '';

    recognition.onresult = (event: any) => {
      let interim = '';
      
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interim += transcript;
        }
      }
      
      // Show interim results to user
      if (interim) {
        setInterimText(interim);
        console.log('[Hotword] Hearing:', interim);
      }

      // Process final result
      if (finalTranscript) {
        const transcript = finalTranscript.toLowerCase().trim();
        setInterimText(''); // Clear interim
        console.log('[Hotword] Final heard:', transcript);

        // Check all alternatives for wake word using fuzzy matching
        let wakeDetected = WAKE_WORD_FUZZY.some(w => transcript.includes(w));
        
        // Also check alternative interpretations
        if (!wakeDetected && event.results[0].length > 1) {
          for (let i = 1; i < event.results[0].length; i++) {
            const alt = event.results[0][i].transcript.toLowerCase().trim();
            if (WAKE_WORD_FUZZY.some(w => alt.includes(w))) {
              wakeDetected = true;
              console.log('[Hotword] Wake word found in alternative:', alt);
              break;
            }
          }
        }

        if (wakeDetected && hotwordActive.current) {
          console.log('[Hotword] Wake word detected! Recording command...');
          setVoiceState('listening');
          startListening();
        } else {
          // Not a wake word, loop again immediately
          if (hotwordActive.current) hotwordListenLoop();
        }
      }
    };

    recognition.onerror = (e: any) => {
      setInterimText(''); // Clear on error
      // network error = no internet for Google speech, fall back to python loop
      if (e.error === 'network') {
        if (!hasLoggedNoNetwork.current) {
          console.warn('[Hotword] No network for browser speech — switching to backend loop (logged once)');
          hasLoggedNoNetwork.current = true;
        }
        if (hotwordActive.current) setTimeout(() => pythonHotwordLoop(), 300);
        return;
      }
      // no-speech just means silence, loop again
      if (hotwordActive.current && !isRecording.current && !speakCooldown.current) {
        setTimeout(() => hotwordListenLoop(), 100);
      }
    };

    recognition.onend = () => {
      setInterimText(''); // Clear on end
      // If no result fired and still active, loop again
      if (hotwordActive.current && !isRecording.current) {
        setTimeout(() => hotwordListenLoop(), 100);
      }
    };

    hotwordRecognition.current = recognition;
    try { recognition.start(); } catch {}
  }, [setVoiceState, startListening, pythonHotwordLoop]);

  // Activate hotword mode — triggered by wave gesture or orb click
  const activateHotwordMode = useCallback(() => {
    if (hotwordActive.current) {
      console.log('[Voice] Hotword mode already active, resetting timer');
    } else {
      console.log('[Voice] Hotword mode activated');
      hotwordActive.current = true;
      networkFallbackLogged.current = false;
      hasLoggedNoNetwork.current = false;
      setVoiceState('hotword');
    }

    // Reset 3-hour hibernation timer
    if (hotwordTimeout.current) clearTimeout(hotwordTimeout.current);
    hotwordTimeout.current = setTimeout(() => {
      console.log('[Voice] Hotword mode timed out — hibernating');
      hotwordActive.current = false;
      if (hotwordRecognition.current) {
        try { hotwordRecognition.current.stop(); } catch {}
      }
      setVoiceState('idle');
    }, HOTWORD_TIMEOUT_MS);

    if (!isRecording.current) {
      hotwordListenLoop();
    }
  }, [setVoiceState, hotwordListenLoop]);

  const manualWake = useCallback(async () => {
    await startListening();
  }, [startListening]);

  // Listen for wave gesture → activate hotword mode (with 2s debounce)
  React.useEffect(() => {
    const handleWake = () => {
      const now = Date.now();
      if (now - lastWaveTime.current < WAVE_DEBOUNCE_MS) {
        console.log('[Voice] Wave debounced — too soon since last wave');
        return;
      }
      lastWaveTime.current = now;
      console.log('[Voice] Wake event received (wave)');
      activateHotwordMode();
    };
    window.addEventListener('jarvis:wake', handleWake);
    return () => window.removeEventListener('jarvis:wake', handleWake);
  }, [activateHotwordMode]);

  useEffect(() => {
    // Autoconnect on mount so proactive messages and dashboard metrics flow
    initWebSocket();
    // Cleanup handled by destructor
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Send text command via WebSocket
  const sendTextCommand = useCallback(async (text: string) => {
    if (!text.trim()) return;
    
    const connected = await initWebSocket();
    if (!connected) {
      console.error('[Voice] Cannot send text - WebSocket not connected');
      return;
    }
    
    setVoiceState('thinking');
    
    // Send text as command
    ws.current?.send(JSON.stringify({
      type: 'command',
      text: text.trim()
    }));
    
    console.log('[Voice] Text command sent:', text);
  }, [initWebSocket, setVoiceState]);

  return (
    <VoiceContext.Provider value={{
      state,
      isOffline,
      lastResponse,
      interimText,
      startListening,
      stopListening: () => setVoiceState('idle'),
      manualWake,
      activateHotwordMode,
      sendTextCommand,
      messages,
      wsConnected
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
