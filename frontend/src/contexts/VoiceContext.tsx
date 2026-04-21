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
const WAKE_WORD_PATTERNS = [
  /\bjarvis\b/,
  /\bhey jarvis\b/,
  /\bokay jarvis\b/,
  /\boperator\b/,
  /\bjervis\b/,
  /\bjarvas\b/,
  /\bjavis\b/,
  /\bjalvis\b/,
  /\bdovis\b/
];
const MAX_RECORDING_MS = 12000;
const SILENCE_CHECK_MS = 200;
const SILENCE_RMS_THRESHOLD = 0.012;
const SILENCE_STOP_MS = 900;

function getWebSocketUrl(): string {
  const configured = import.meta.env.VITE_OPERATOR_WS_URL as string | undefined;
  if (configured && configured.trim()) {
    return configured.trim();
  }
  const host = window.location.host;
  if (host.includes('.ngrok-free.app') || host.includes('.ngrok-free.dev')) {
    return `wss://${host}/ws`;
  }
  return 'ws://localhost:8765';
}

function getApiBaseUrl(): string {
  const configured = import.meta.env.VITE_OPERATOR_API_URL as string | undefined;
  if (configured && configured.trim()) {
    return configured.trim().replace(/\/$/, '');
  }
  const host = window.location.host;
  if (host.includes('.ngrok-free.app') || host.includes('.ngrok-free.dev')) {
    return `${window.location.protocol}//${host}`;
  }
  return 'http://localhost:5050';
}

// TTS duration estimation removed — now event-driven via `tts_done` WebSocket event


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

function hasWakeWord(text: string): boolean {
  const normalized = text.toLowerCase().trim();
  return WAKE_WORD_PATTERNS.some((pattern) => pattern.test(normalized));
}

export const VoiceProvider: React.FC<VoiceProviderProps> = ({ children }) => {
  const [state, setState] = useState<VoiceState>('idle');
  const [isOffline, setIsOffline] = useState(false);
  const [lastResponse, setLastResponse] = useState('');
  const [messages, setMessages] = useState<any[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [interimText, setInterimText] = useState('');

  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const audioChunks = useRef<Blob[]>([]);
  const ws = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 3;
  const reconnectDelay = 5000;
  const isRecording = useRef(false);

  const hotwordRecognition = useRef<any>(null);
  const hotwordActive = useRef(false);
  const hotwordTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasLoggedNoNetwork = useRef(false);

  const lastWaveTime = useRef(0);
  const WAVE_DEBOUNCE_MS = 2000;

  const isSpeakingRef = useRef(false);
  const speakCooldown = useRef(false);
  const isConnecting = useRef(false);

  // FIX: Track ongoing TTS timeout so we can cancel it if tts_fallback arrives
  const ttsDurationTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const recordingTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const silenceInterval = useRef<ReturnType<typeof setInterval> | null>(null);
  const wakeEngineMode = useRef<'browser' | 'backend'>('browser');
  const lastWakeTriggerAt = useRef(0);
  const WAKE_DEBOUNCE_MS = 2500;

  const setVoiceState = useCallback((newState: VoiceState, offline = false) => {
    setState(newState);
    setIsOffline(offline);
  }, []);

  const reportWakeTelemetry = useCallback((event: string, detail?: string) => {
    ws.current?.send(JSON.stringify({
      type: 'wake_telemetry',
      event,
      detail: detail || null,
      mode: wakeEngineMode.current,
      ts: Date.now(),
    }));
  }, []);

  const canTriggerWake = useCallback(() => {
    const now = Date.now();
    if (now - lastWakeTriggerAt.current < WAKE_DEBOUNCE_MS) return false;
    lastWakeTriggerAt.current = now;
    return true;
  }, []);


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
              /**
               * Server TTS is active — the backend will send a `tts_done`
               * event when pyttsx3 finishes speaking. We set a safety timeout
               * (60s) in case the event is lost, but normally tts_done arrives
               * and cancels this timeout, giving us precise synchronization.
               */
              console.log(`[Voice] Server TTS active — waiting for tts_done event`);
              isSpeakingRef.current = true;
              speakCooldown.current = true;

              // Clear any previous timeout
              if (ttsDurationTimeout.current) {
                clearTimeout(ttsDurationTimeout.current);
              }

              // Safety fallback: if tts_done never arrives, recover after 60s
              ttsDurationTimeout.current = setTimeout(() => {
                console.warn('[Voice] tts_done never arrived — recovering after safety timeout');
                isSpeakingRef.current = false;
                speakCooldown.current = false;
                if (hotwordActive.current) {
                  setVoiceState('hotword');
                  hotwordListenLoop();
                } else {
                  setVoiceState('idle');
                }
              }, 60000);

            } else {
              // Browser TTS (server didn't handle it)
              const cleanText = cleanTextForSpeech(responseText);
              speak(cleanText, () => {
                if (hotwordActive.current) {
                  setVoiceState('hotword');
                  hotwordListenLoop();
                } else {
                  setVoiceState('idle');
                }
              });
            }

          } else if (data.type === 'tts_done') {
            /**
             * Server TTS finished speaking — this is the real signal.
             * Cancel the safety timeout and transition state immediately.
             */
            console.log('[Voice] Server TTS finished (tts_done received)');
            if (ttsDurationTimeout.current) {
              clearTimeout(ttsDurationTimeout.current);
              ttsDurationTimeout.current = null;
            }
            isSpeakingRef.current = false;
            speakCooldown.current = false;
            if (hotwordActive.current) {
              setVoiceState('hotword');
              hotwordListenLoop();
            } else {
              setVoiceState('idle');
            }

          } else if (data.type === 'tts_fallback') {
            /**
             * Server TTS failed — cancel the safety timeout and
             * use browser TTS instead.
             */
            console.log(`[Voice] Server TTS failed (${data.reason}) — using browser fallback`);

            if (ttsDurationTimeout.current) {
              clearTimeout(ttsDurationTimeout.current);
              ttsDurationTimeout.current = null;
            }

            const fallbackText = data.text || "I'm sorry sir, I didn't catch that.";
            const cleanText = cleanTextForSpeech(fallbackText);
            setVoiceState('speaking');
            speak(cleanText, () => {
              if (hotwordActive.current) {
                setVoiceState('hotword');
                hotwordListenLoop();
              } else {
                setVoiceState('idle');
              }
            });

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
  }, [isOffline, setVoiceState]);

  /**
   * Browser speech synthesis with better voice selection and error handling.
   * Tries British male → any en-GB → any English → system default.
   */
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
        // Voices not loaded yet — wait and retry
        setTimeout(trySpeak, 100);
        return;
      }

      // Priority: British male → en-GB → any English
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
        // 'interrupted' is normal when we cancel() — don't log as error
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
      setTimeout(() => {
        speakCooldown.current = false;
        onDone?.();
      }, 1500); // Small cooldown so mic doesn't pick up tail end
    });
  }, [speakWithBrowserTTS]);

  const sendAudioForTranscription = useCallback(async (stream?: MediaStream) => {
    try {
      const audioBlob = new Blob(audioChunks.current, { type: 'audio/webm' });
      if (audioBlob.size === 0) {
        stream?.getTracks().forEach(t => t.stop());
        setVoiceState(hotwordActive.current ? 'hotword' : 'idle');
        return;
      }

      const formData = new FormData();
      formData.append('audio', audioBlob, 'recording.webm');

      const response = await fetch(`${getApiBaseUrl()}/transcribe`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log('[Voice] Transcription:', data.text);

      const lower = (data.text || '').toLowerCase().trim();
      const stopWords = ['stop', 'shut up', 'be quiet', 'silence', 'stop talking', 'quiet', 'enough'];
      if (stopWords.some(w => lower.includes(w))) {
        window.speechSynthesis.cancel();
        if (ttsDurationTimeout.current) clearTimeout(ttsDurationTimeout.current);
        isSpeakingRef.current = false;
        speakCooldown.current = false;
        hotwordActive.current = false;
        if (hotwordTimeout.current) clearTimeout(hotwordTimeout.current);
        setVoiceState('idle');
        return;
      }

      if (data.text?.trim()) {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setVoiceState]);

  const startListening = useCallback(async () => {
    if (isRecording.current || isSpeakingRef.current || speakCooldown.current) return;

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
        if (recordingTimeout.current) {
          clearTimeout(recordingTimeout.current);
          recordingTimeout.current = null;
        }
        if (silenceInterval.current) {
          clearInterval(silenceInterval.current);
          silenceInterval.current = null;
        }
        setVoiceState('thinking');
        stream.getTracks().forEach(track => track.stop());
        try { await audioContext.close(); } catch { /* ignore */ }
        await sendAudioForTranscription(stream);
      };

      const audioContext = new AudioContext();
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 1024;
      source.connect(analyser);
      const data = new Uint8Array(analyser.fftSize);

      const stopRecording = () => {
        if (recordingTimeout.current) {
          clearTimeout(recordingTimeout.current);
          recordingTimeout.current = null;
        }
        if (silenceInterval.current) {
          clearInterval(silenceInterval.current);
          silenceInterval.current = null;
        }
        if (mediaRecorder.current && isRecording.current) {
          mediaRecorder.current.stop();
        }
      };

      let lastSpeechAt = Date.now();
      silenceInterval.current = setInterval(() => {
        if (!isRecording.current) return;
        analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) {
          const centered = (data[i] - 128) / 128;
          sum += centered * centered;
        }
        const rms = Math.sqrt(sum / data.length);
        const now = Date.now();
        if (rms > SILENCE_RMS_THRESHOLD) {
          lastSpeechAt = now;
          return;
        }
        if (now - lastSpeechAt >= SILENCE_STOP_MS) {
          stopRecording();
        }
      }, SILENCE_CHECK_MS);

      mediaRecorder.current.start();
      isRecording.current = true;
      setVoiceState('listening');
      console.log('[Voice] Recording started');

      recordingTimeout.current = setTimeout(() => {
        stopRecording();
      }, MAX_RECORDING_MS);

    } catch (err) {
      console.error('[Voice] Failed to start recording:', err);
      setVoiceState('idle');
    }
  }, [initWebSocket, sendAudioForTranscription, setVoiceState]);

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
          const res = await fetch(`${getApiBaseUrl()}/transcribe`, { method: 'POST', body: formData });
          const data = await res.json();
          const transcript = (data.text || '').toLowerCase().trim();
          console.log('[Hotword-Python] Heard:', transcript);

          const wakeDetected = hasWakeWord(transcript);
          if (wakeDetected && hotwordActive.current) {
            if (!canTriggerWake()) return;
            reportWakeTelemetry('wake_detected', 'backend_transcribe');
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
  }, [canTriggerWake, initWebSocket, reportWakeTelemetry, setVoiceState, startListening]);

  const hotwordListenLoop = useCallback(() => {
    if (!hotwordActive.current || isRecording.current || isSpeakingRef.current || speakCooldown.current) return;

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn('[Hotword] SpeechRecognition not available — using backend loop');
      wakeEngineMode.current = 'backend';
      reportWakeTelemetry('wake_fallback', 'browser_unavailable');
      pythonHotwordLoop();
      return;
    }
    wakeEngineMode.current = 'browser';

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-GB';
    recognition.maxAlternatives = 3;

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

      if (interim) setInterimText(interim);

      if (finalTranscript) {
        const transcript = finalTranscript.toLowerCase().trim();
        setInterimText('');
        console.log('[Hotword] Final heard:', transcript);

        let wakeDetected = hasWakeWord(transcript);

        if (!wakeDetected && event.results[0].length > 1) {
          for (let i = 1; i < event.results[0].length; i++) {
            const alt = event.results[0][i].transcript.toLowerCase().trim();
            if (hasWakeWord(alt)) {
              wakeDetected = true;
              console.log('[Hotword] Wake word in alternative:', alt);
              break;
            }
          }
        }

        if (wakeDetected && hotwordActive.current) {
          if (!canTriggerWake()) return;
          reportWakeTelemetry('wake_detected', 'browser_speech');
          setVoiceState('listening');
          startListening();
        } else if (hotwordActive.current) {
          hotwordListenLoop();
        }
      }
    };

    recognition.onerror = (e: any) => {
      setInterimText('');
      if (e.error === 'network') {
        if (!hasLoggedNoNetwork.current) {
          console.warn('[Hotword] No network for browser speech — switching to backend loop');
          hasLoggedNoNetwork.current = true;
        }
        wakeEngineMode.current = 'backend';
        reportWakeTelemetry('wake_fallback', 'network_error');
        if (hotwordActive.current) setTimeout(() => pythonHotwordLoop(), 300);
        return;
      }
      if (hotwordActive.current && !isRecording.current && !speakCooldown.current) {
        setTimeout(() => hotwordListenLoop(), 100);
      }
    };

    recognition.onend = () => {
      setInterimText('');
      if (hotwordActive.current && !isRecording.current) {
        setTimeout(() => hotwordListenLoop(), 100);
      }
    };

    hotwordRecognition.current = recognition;
    try { recognition.start(); } catch { /* ignore */ }
  }, [canTriggerWake, pythonHotwordLoop, reportWakeTelemetry, setVoiceState, startListening]);

  const activateHotwordMode = useCallback(() => {
    if (!hotwordActive.current) {
      console.log('[Voice] Hotword mode activated');
      hotwordActive.current = true;
      hasLoggedNoNetwork.current = false;
      setVoiceState('hotword');
    } else {
      console.log('[Voice] Hotword mode — resetting timer');
    }

    if (hotwordTimeout.current) clearTimeout(hotwordTimeout.current);
    hotwordTimeout.current = setTimeout(() => {
      console.log('[Voice] Hotword mode timed out');
      hotwordActive.current = false;
      try { hotwordRecognition.current?.stop(); } catch { /* ignore */ }
      setVoiceState('idle');
    }, HOTWORD_TIMEOUT_MS);

    if (!isRecording.current) hotwordListenLoop();
  }, [hotwordListenLoop, setVoiceState]);

  const manualWake = useCallback(async () => {
    await startListening();
  }, [startListening]);

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

  // Listen for wave gesture
  useEffect(() => {
    const handleWake = () => {
      const now = Date.now();
      if (now - lastWaveTime.current < WAVE_DEBOUNCE_MS) return;
      lastWaveTime.current = now;
      console.log('[Voice] Wake event from wave gesture');
      activateHotwordMode();
    };
    window.addEventListener('jarvis:wake', handleWake);
    return () => window.removeEventListener('jarvis:wake', handleWake);
  }, [activateHotwordMode]);

  // Autoconnect on mount
  useEffect(() => {
    initWebSocket();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);


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