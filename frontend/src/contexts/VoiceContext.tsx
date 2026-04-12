import React, { createContext, useContext, useState, useCallback, useRef, ReactNode } from 'react';

export type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'offline';

interface VoiceContextType {
  state: VoiceState;
  isOffline: boolean;
  lastResponse: string;
  startListening: () => Promise<void>;
  stopListening: () => void;
  manualWake: () => Promise<void>;
}

const VoiceContext = createContext<VoiceContextType | undefined>(undefined);

interface VoiceProviderProps {
  children: ReactNode;
}

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
        console.log('[Voice] Previously offline, attempting reconnect...');
        setIsOffline(false);
        reconnectAttempts.current = 0;
      }

      const wsUrl = 'ws://localhost:8765';
      console.log(`[Voice] WebSocket attempt ${reconnectAttempts.current + 1}/${maxReconnectAttempts}`);

      ws.current = new WebSocket(wsUrl);
      let connected = false;

      ws.current.onopen = () => {
        console.log('[Voice] WebSocket connected');
        reconnectAttempts.current = 0;
        setIsOffline(false);
        connected = true;
        setVoiceState('idle');
        resolve(true);
      };

      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'response') {
            setLastResponse(data.text);
            setVoiceState('speaking');
            speak(data.text);
            setTimeout(() => {
              setVoiceState('idle');
            }, 2000);
          } else if (data.type === 'stream_chunk') {
            console.log('[Voice] Stream chunk received');
          } else if (data.type === 'state') {
            setVoiceState(data.state);
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
        if (connected) {
          console.log('[Voice] WebSocket closed unexpectedly');
        }

        reconnectAttempts.current++;

        if (reconnectAttempts.current >= maxReconnectAttempts) {
          console.error('[Voice] Max reconnection attempts reached. Jarvis is offline.');
          setIsOffline(true);
          setVoiceState('idle', true);
          resolve(false);
          return;
        }

        if (!connected && !isOffline) {
          console.log(`[Voice] Retrying in ${reconnectDelay / 1000}s...`);
          setTimeout(() => {
            initWebSocket().then(resolve);
          }, reconnectDelay);
        }
      };

      // Timeout for connection attempt
      setTimeout(() => {
        if (!connected && ws.current?.readyState !== WebSocket.OPEN) {
          ws.current?.close();
        }
      }, 3000);
    });
  }, [isOffline, setVoiceState]);

  const speak = useCallback((text: string) => {
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.9;
    utterance.pitch = 1.1;

    const voices = window.speechSynthesis.getVoices();
    const britishVoice = voices.find(v => v.lang === 'en-GB' || v.name.includes('British'));
    if (britishVoice) {
      utterance.voice = britishVoice;
    }

    utterance.onend = () => {
      console.log('[Voice] Finished speaking');
    };

    utterance.onerror = (e) => {
      console.error('[Voice] Speech error:', e);
    };

    window.speechSynthesis.speak(utterance);
  }, []);

  const sendAudioForTranscription = useCallback(async () => {
    try {
      const audioBlob = new Blob(audioChunks.current, { type: 'audio/webm' });
      console.log('[Voice] Audio blob size:', audioBlob.size, 'bytes');

      if (audioBlob.size === 0) {
        console.log('[Voice] No audio recorded');
        setVoiceState('idle');
        return;
      }

      const formData = new FormData();
      formData.append('audio', audioBlob, 'recording.webm');

      console.log('[Voice] Sending audio to backend...');
      const response = await fetch('http://localhost:5050/transcribe', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log('[Voice] Transcription received:', data.text);

      if (data.text && data.text.trim()) {
        // Send transcribed text via WebSocket
        ws.current?.send(JSON.stringify({
          type: 'voice_command',
          text: data.text
        }));
      } else {
        console.log('[Voice] No speech detected');
        setVoiceState('idle');
      }
    } catch (error) {
      console.error('[Voice] Transcription error:', error);
      setVoiceState('idle');
    }

    audioChunks.current = [];
  }, [setVoiceState]);

  const startListening = useCallback(async () => {
    if (isRecording.current) {
      console.log('[Voice] Already recording');
      return;
    }

    // Initialize WebSocket if not connected
    const connected = await initWebSocket();

    if (!connected) {
      console.error('[Voice] Cannot start recording - WebSocket unavailable');
      return;
    }

    try {
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      console.log('[Voice] Microphone access granted');

      // Create MediaRecorder
      mediaRecorder.current = new MediaRecorder(stream);
      audioChunks.current = [];

      mediaRecorder.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunks.current.push(event.data);
        }
      };

      mediaRecorder.current.onstop = async () => {
        console.log('[Voice] Recording stopped, processing...');
        isRecording.current = false;
        setVoiceState('thinking');

        // Stop all tracks to release microphone
        stream.getTracks().forEach(track => track.stop());

        // Send audio to backend for transcription
        await sendAudioForTranscription();
      };

      // Start recording
      mediaRecorder.current.start();
      isRecording.current = true;
      setVoiceState('listening');
      console.log('[Voice] Recording started (5 seconds)');

      // Stop after exactly 5 seconds
      setTimeout(() => {
        if (mediaRecorder.current && isRecording.current) {
          mediaRecorder.current.stop();
          console.log('[Voice] Recording auto-stopped after 5 seconds');
        }
      }, 5000);

    } catch (err) {
      console.error('[Voice] Failed to start recording:', err);
      setVoiceState('idle');
      alert('Please allow microphone access to use voice features.');
    }
  }, [initWebSocket, sendAudioForTranscription, setVoiceState]);

  const stopListening = useCallback(() => {
    if (mediaRecorder.current && isRecording.current) {
      mediaRecorder.current.stop();
    }
    if (ws.current) {
      ws.current.close();
    }
  }, []);

  const manualWake = useCallback(async () => {
    await startListening();
  }, [startListening]);

  const value: VoiceContextType = {
    state,
    isOffline,
    lastResponse,
    startListening,
    stopListening,
    manualWake,
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
