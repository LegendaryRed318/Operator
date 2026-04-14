import React, { createContext, useContext, useState, useCallback, useRef, ReactNode } from 'react';

export type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'offline' | 'hotword';

interface VoiceContextType {
  state: VoiceState;
  isOffline: boolean;
  lastResponse: string;
  startListening: () => Promise<void>;
  stopListening: () => void;
  manualWake: () => Promise<void>;
  activateHotwordMode: () => void;
}

const VoiceContext = createContext<VoiceContextType | undefined>(undefined);

interface VoiceProviderProps {
  children: ReactNode;
}

const HOTWORD_TIMEOUT_MS = 3 * 60 * 60 * 1000; // 3 hours
const WAKE_WORDS = ['jarvis', 'operator'];

export const VoiceProvider: React.FC<VoiceProviderProps> = ({ children }) => {
  const [state, setState] = useState<VoiceState>('idle');
  const [isOffline, setIsOffline] = useState(false);
  const [lastResponse, setLastResponse] = useState('');

  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const audioChunks = useRef<Blob[]>([]);
  const ws = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 3;
  const reconnectDelay = 5000;
  const isRecording = useRef(false);
  const isSpeaking = useRef(false);
  const speakCooldown = useRef(false);

  // Hotword refs
  const hotwordRecognition = useRef<any>(null);
  const hotwordActive = useRef(false);
  const hotwordTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Prevents the "no network" fallback warning from spamming the console
  const networkFallbackLogged = useRef(false);

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

      if (isOffline) {
        setIsOffline(false);
        reconnectAttempts.current = 0;
      }

      const wsUrl = 'ws://localhost:8765';
      ws.current = new WebSocket(wsUrl);
      let connected = false;

      ws.current.onopen = () => {
        console.log('[Voice] WebSocket connected');
        reconnectAttempts.current = 0;
        setIsOffline(false);
        connected = true;
        resolve(true);
      };

      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'response') {
            setLastResponse(data.text);
            setVoiceState('speaking');
            speak(data.text, () => {
              // After speaking, go straight back to hotword listening
              if (hotwordActive.current) {
                setVoiceState('hotword');
                hotwordListenLoop();  // straight back to listening
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
        reconnectAttempts.current++;
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

  const speak = useCallback((text: string, onDone?: () => void) => {
    isSpeaking.current = true;
    speakCooldown.current = true;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.9;
    utterance.pitch = 1.1;

    const voices = window.speechSynthesis.getVoices();
    const britishVoice = voices.find(v => v.lang === 'en-GB' || v.name.includes('British'));
    if (britishVoice) utterance.voice = britishVoice;

    // Watchdog: Chrome sometimes never fires utterance.onend for long responses.
    // If that happens, speakCooldown stays true forever and Jarvis goes deaf.
    // Estimate duration (avg ~130 WPM) + 3s cooldown + 5s buffer.
    const wordCount = text.split(/\s+/).length;
    const estimatedMs = (wordCount / 130) * 60_000 + 3000 + 5000;
    const watchdog = setTimeout(() => {
      if (speakCooldown.current) {
        console.warn('[Voice] speechSynthesis onend never fired — forcing cooldown reset');
        isSpeaking.current = false;
        speakCooldown.current = false;
        onDone?.();
      }
    }, estimatedMs);

    utterance.onend = () => {
      clearTimeout(watchdog);
      console.log('[Voice] Finished speaking');
      isSpeaking.current = false;
      // 3 second cooldown so the mic doesn't pick up Jarvis's own voice
      setTimeout(() => {
        speakCooldown.current = false;
        onDone?.();
      }, 3000);
    };
    utterance.onerror = () => {
      clearTimeout(watchdog);
      isSpeaking.current = false;
      speakCooldown.current = false;
      onDone?.();
    };

    window.speechSynthesis.speak(utterance);
  }, []);

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

      // Stop command — tears down hotword mode immediately
      if (data.text && data.text.toLowerCase().includes('stop')) {
        console.log('[Voice] Stop command received');
        hotwordActive.current = false;
        speakCooldown.current = false;
        window.speechSynthesis.cancel();
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
    if (isRecording.current) return;

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
    if (!hotwordActive.current || isRecording.current || isSpeaking.current || speakCooldown.current) return;

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

          if (WAKE_WORDS.some(w => transcript.includes(w)) && hotwordActive.current) {
            console.log('[Hotword] Wake word detected! Recording command...');
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

  // Fast browser-based hotword loop
  const hotwordListenLoop = useCallback(() => {
    if (!hotwordActive.current || isRecording.current || isSpeaking.current || speakCooldown.current) return;

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn('[Hotword] SpeechRecognition not available, using fallback');
      pythonHotwordLoop();
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;      // short burst, not continuous
    recognition.interimResults = false;
    recognition.lang = 'en-GB';
    recognition.maxAlternatives = 1;

    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript.toLowerCase().trim();
      console.log('[Hotword] Heard:', transcript);

      const wakeDetected = WAKE_WORDS.some(w => transcript.includes(w));
      if (wakeDetected && hotwordActive.current) {
        console.log('[Hotword] Wake word detected! Recording command...');
        setVoiceState('listening');
        startListening();
      } else {
        // Not a wake word, loop again immediately
        if (hotwordActive.current) hotwordListenLoop();
      }
    };

    recognition.onerror = (e: any) => {
      // network error = no internet for Google speech, fall back to python loop
      if (e.error === 'network') {
        if (!networkFallbackLogged.current) {
          console.warn('[Hotword] No network for browser speech — switching to backend loop (logged once)');
          networkFallbackLogged.current = true;
        }
        if (hotwordActive.current) setTimeout(() => pythonHotwordLoop(), 300);
        return;
      }
      // no-speech just means silence, loop again
      if (hotwordActive.current && !isRecording.current) {
        setTimeout(() => hotwordListenLoop(), 100);
      }
    };

    recognition.onend = () => {
      // If no result fired and still active, loop again
      if (hotwordActive.current && !isRecording.current) {
        setTimeout(() => hotwordListenLoop(), 100);
      }
    };

    hotwordRecognition.current = recognition;
    try { recognition.start(); } catch {}
  }, [setVoiceState, startListening, pythonHotwordLoop]);

  // Activate hotword mode — triggered by wave gesture
  const activateHotwordMode = useCallback(() => {
    if (hotwordActive.current) {
      console.log('[Voice] Hotword mode already active, resetting timer');
    } else {
      console.log('[Voice] Hotword mode activated — say "Jarvis" to command');
      hotwordActive.current = true;
      networkFallbackLogged.current = false; // reset per-session log gate
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

    // Start the hotword listen loop
    if (!isRecording.current) {
      hotwordListenLoop();
    }
  }, [setVoiceState, hotwordListenLoop]);

  const stopListening = useCallback(() => {
    if (mediaRecorder.current && isRecording.current) mediaRecorder.current.stop();
    hotwordActive.current = false;
    if (hotwordRecognition.current) {
      try { hotwordRecognition.current.stop(); } catch {}
    }
    if (hotwordTimeout.current) clearTimeout(hotwordTimeout.current);
    if (ws.current) ws.current.close();
  }, []);

  const manualWake = useCallback(async () => {
    await startListening();
  }, [startListening]);

  // Listen for wave gesture → activate hotword mode
  React.useEffect(() => {
    const handleWake = () => {
      console.log('[Voice] Wake event received');
      activateHotwordMode();
    };
    window.addEventListener('jarvis:wake', handleWake);
    return () => window.removeEventListener('jarvis:wake', handleWake);
  }, [activateHotwordMode]);

  const value: VoiceContextType = {
    state,
    isOffline,
    lastResponse,
    startListening,
    stopListening,
    manualWake,
    activateHotwordMode,
  };

  return (
    <VoiceContext.Provider value={value}>
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
