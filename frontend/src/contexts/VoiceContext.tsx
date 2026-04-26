import React, { createContext, useContext, useState, useCallback, useRef, ReactNode, useEffect } from 'react';
import { getWebSocketUrl, getApiBaseUrl } from '../utils/urls';

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
  isConversationMode: boolean;
  toggleConversationMode: () => void;
}

const VoiceContext = createContext<VoiceContextType | undefined>(undefined);

interface VoiceProviderProps {
  children: ReactNode;
}

const HOTWORD_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes
const FOLLOW_UP_WINDOW_MS = 20 * 1000; // 20 second conversation follow-up window
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
const MAX_RECORDING_MS = 8000;
const SILENCE_CHECK_MS = 200;
const SILENCE_RMS_THRESHOLD = 0.012;
const SILENCE_STOP_MS = 600;

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
  const [isConversationMode, setIsConversationMode] = useState(false);

  const stateWatchdogRef = useRef<{ state: VoiceState; since: number }>({ state: 'idle', since: Date.now() });

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

  const ttsDurationTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const recordingTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const silenceInterval = useRef<ReturnType<typeof setInterval> | null>(null);
  const wakeEngineMode = useRef<'browser' | 'backend'>('browser');
  const lastWakeTriggerAt = useRef(0);
  const WAKE_DEBOUNCE_MS = 2500;

  const followUpTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const followUpTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  // Priority 5: Orb state watchdog
  useEffect(() => {
    const watchdog = setInterval(() => {
      const { state: trackedState, since } = stateWatchdogRef.current;
      const elapsed = Date.now() - since;
      
      if (trackedState === 'thinking' && elapsed > 15000) {
        console.warn('[Watchdog] Stuck in thinking state for >15s. Forcing reset.');
        setVoiceState(hotwordActive.current ? 'hotword' : 'idle');
      } else if (trackedState === 'speaking' && elapsed > 20000 && !isSpeakingRef.current) {
        console.warn('[Watchdog] Stuck in speaking state for >20s. Forcing reset.');
        setVoiceState(hotwordActive.current ? 'hotword' : 'idle');
      }
    }, 5000);
    return () => clearInterval(watchdog);
  }, [setVoiceState]);

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

  const onSpeechFinished = useCallback(() => {
    isSpeakingRef.current = false;
    if (ttsDurationTimeout.current) {
      clearTimeout(ttsDurationTimeout.current);
      ttsDurationTimeout.current = null;
    }

    // Start the 20-second conversation follow-up window
    if (!isConversationModeRef.current) {
      setIsConversationMode(true);
      console.log('[Voice] Starting follow-up window (20s) — auto-listening enabled');
    }

    // Reset the follow-up timer
    if (followUpTimeoutRef.current) clearTimeout(followUpTimeoutRef.current);
    if (followUpTimerRef.current) clearTimeout(followUpTimerRef.current);

    followUpTimeoutRef.current = setTimeout(() => {
      console.log('[Voice] Follow-up window expired — returning to idle');
      setIsConversationMode(false);
      followUpTimeoutRef.current = null;
      followUpTimerRef.current = null;
      if (!hotwordActive.current) {
        setVoiceState('idle');
      }
    }, FOLLOW_UP_WINDOW_MS);

    // Give a small cooldown before transitioning state
    setTimeout(() => {
      speakCooldown.current = false;
      if (followUpTimeoutRef.current && hotwordActive.current) {
        // In hotword mode, stay in hotword after speaking
        setVoiceState('hotword');
      } else if (followUpTimeoutRef.current) {
        // In conversation mode, stay in listening for the follow-up window
        console.log('[Voice] Follow-up: auto-triggering mic');
        setVoiceState('listening');
      } else if (hotwordActive.current) {
        setVoiceState('hotword');
      } else {
        setVoiceState('idle');
      }
    }, 900);
  }, [setVoiceState]);

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
              speakCooldown.current = true;

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
            console.log('[Voice] Server TTS finished (tts_done received)');
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
          } else if (data.type === 'start_note_capture') {
            console.log('[Voice] Starting note capture recording');
            // Start a 10-second VAD recording session for note taking
            startNoteCaptureRecording();
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
        if (followUpTimeoutRef.current) clearTimeout(followUpTimeoutRef.current);
        if (followUpTimerRef.current) clearTimeout(followUpTimerRef.current);
        followUpTimeoutRef.current = null;
        followUpTimerRef.current = null;
        isSpeakingRef.current = false;
        speakCooldown.current = false;
        hotwordActive.current = false;
        if (hotwordTimeout.current) clearTimeout(hotwordTimeout.current);
        setVoiceState('idle');
        setIsConversationMode(false);
        return;
      }

      if (data.text?.trim()) {
        // Reset the follow-up window when user speaks
        if (followUpTimeoutRef.current) {
          clearTimeout(followUpTimeoutRef.current);
          followUpTimeoutRef.current = setTimeout(() => {
            console.log('[Voice] Follow-up window expired after user response');
            setIsConversationMode(false);
            followUpTimeoutRef.current = null;
            followUpTimerRef.current = null;
            if (!hotwordActive.current) setVoiceState('idle');
          }, FOLLOW_UP_WINDOW_MS);
        }
        ws.current?.send(JSON.stringify({ type: 'voice_command', text: data.text }));
      } else {
        setVoiceState(hotwordActive.current ? 'hotword' : 'idle');
      }
    } catch (error) {
      console.error('[Voice] Transcription error:', error);
      setVoiceState(hotwordActive.current ? 'hotword' : 'idle');
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

  // Special 10-second VAD recording for vault note capture
  const startNoteCaptureRecording = useCallback(async () => {
    if (isRecording.current) return;
    
    const connected = await initWebSocket();
    if (!connected) return;

    try {
      setVoiceState('listening');
      console.log('[Voice] Note capture recording started (10s max)');

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const audioCtx = new AudioContext();
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);

      const recorder = new MediaRecorder(stream);
      const chunks: Blob[] = [];

      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
      
      recorder.onstop = async () => {
        isRecording.current = false;
        stream.getTracks().forEach(t => t.stop());
        audioCtx.close();
        if (vadInterval.current) clearInterval(vadInterval.current);

        const blob = new Blob(chunks, { type: 'audio/webm' });
        if (blob.size < 1000) {
          setVoiceState('idle');
          return;
        }

        try {
          // Transcribe the note
          const formData = new FormData();
          formData.append('audio', blob, 'note.webm');
          const res = await fetch(`${getApiBaseUrl()}/transcribe`, { method: 'POST', body: formData });
          const data = await res.json();
          const transcript = data.text || '';
          
          console.log('[Voice] Note captured:', transcript);
          
          // Send back to server for saving to vault
          ws.current?.send(JSON.stringify({
            type: 'note_capture_done',
            transcript: transcript
          }));
        } catch (err) {
          console.error('[Voice] Note transcription failed:', err);
          setVoiceState('idle');
        }
      };

      recorder.start();
      isRecording.current = true;

      // VAD: Stop after 1.2s of silence or max 10 seconds
      const dataArray = new Uint8Array(analyser.ffftSize || 2048);
      let silenceStart = Date.now();
      const MAX_NOTE_MS = 10000;
      const SILENCE_MS = 1200;
      const startTime = Date.now();

      vadInterval.current = window.setInterval(() => {
        analyser.getByteTimeDomainData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) sum += Math.abs(dataArray[i] - 128);
        const average = sum / dataArray.length;
        const rms = average / 128;

        if (rms < SILENCE_RMS_THRESHOLD) {
          if (Date.now() - silenceStart > SILENCE_MS) {
            if (recorder.state === 'recording') recorder.stop();
          }
        } else {
          silenceStart = Date.now();
        }

        if (Date.now() - startTime > MAX_NOTE_MS) {
          if (recorder.state === 'recording') recorder.stop();
        }
      }, SILENCE_CHECK_MS);

    } catch (err) {
      console.error('[Voice] Note capture failed:', err);
      setVoiceState('idle');
    }
  }, [initWebSocket, setVoiceState]);

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

  // Hook up state-driven triggers that used to be inside onSpeechFinished to avoid dependency cycles
  useEffect(() => {
    if (state === 'listening' && !isRecording.current && !isSpeakingRef.current) {
      startListening();
    } else if (state === 'hotword' && !isRecording.current && !isSpeakingRef.current && hotwordActive.current) {
      hotwordListenLoop();
    }
  }, [state, startListening, hotwordListenLoop]);

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
      wsConnected,
      isConversationMode,
      toggleConversationMode
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