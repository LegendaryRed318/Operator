// voice.ts - Jarvis voice interface
// WebSocket with max 3 retries, MediaRecorder for audio, NO SpeechRecognition API

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

export class VoiceController {
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private ws: WebSocket | null = null;
  private onStateChange: (state: string, offline?: boolean) => void;
  private onResponse: (text: string) => void;
  private isRecording = false;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 3;
  private reconnectDelay = 5000;
  private isOffline = false;

  constructor(onStateChange: (state: string, offline?: boolean) => void, onResponse: (text: string) => void) {
    this.onStateChange = onStateChange;
    this.onResponse = onResponse;
    // Do NOT connect WebSocket on construction - wait for first orb click
    console.log('[Voice] Controller initialized, waiting for orb click');
  }

  private initWebSocket(): Promise<boolean> {
    return new Promise((resolve) => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        resolve(true);
        return;
      }

      if (this.isOffline) {
        console.log('[Voice] Previously offline, attempting reconnect...');
        this.isOffline = false;
        this.reconnectAttempts = 0;
      }

      const wsUrl = getWebSocketUrl();
      const isRemote = wsUrl.startsWith('wss://');
      
      console.log(`[Voice] WebSocket attempt ${this.reconnectAttempts + 1}/${this.maxReconnectAttempts} to ${wsUrl}`);

      this.ws = new WebSocket(wsUrl);
      let connected = false;

      this.ws.onopen = () => {
        // Log connection type for debugging
        if (isRemote) {
          console.log('[Voice] Connected to JARVIS via remote ngrok (wss)');
        } else {
          console.log('[Voice] Connected to JARVIS locally (ws)');
        }
        this.reconnectAttempts = 0;
        this.isOffline = false;
        connected = true;
        this.onStateChange('idle');
        resolve(true);
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'response') {
            this.onResponse(data.text);
            this.onStateChange('speaking');
            this.speak(data.text);
            setTimeout(() => {
              this.onStateChange('idle');
            }, 2000);
          } else if (data.type === 'stream_chunk') {
            // Optional: handle streaming chunks for live UI updates
            console.log('[Voice] Stream chunk received');
          } else if (data.type === 'state') {
            this.onStateChange(data.state);
          } else if (data.type === 'ack') {
            console.log('[Voice]', data.message);
          }
        } catch (e) {
          console.error('[Voice] Failed to parse message:', e);
        }
      };

      this.ws.onerror = (err) => {
        console.error('[Voice] WebSocket error:', err);
      };

      this.ws.onclose = () => {
        if (connected) {
          console.log('[Voice] WebSocket closed unexpectedly');
        }
        
        this.reconnectAttempts++;
        
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
          console.error('[Voice] Max reconnection attempts reached. Jarvis is offline.');
          this.isOffline = true;
          this.onStateChange('idle', true); // true = offline
          resolve(false);
          return;
        }

        if (!connected && !this.isOffline) {
          console.log(`[Voice] Retrying in ${this.reconnectDelay / 1000}s...`);
          setTimeout(() => {
            this.initWebSocket().then(resolve);
          }, this.reconnectDelay);
        }
      };

      // Timeout for connection attempt
      setTimeout(() => {
        if (!connected && this.ws?.readyState !== WebSocket.OPEN) {
          this.ws?.close();
        }
      }, 3000);
    });
  }

  // Called when orb is clicked - connect WebSocket then start recording
  public async startRecording() {
    if (this.isRecording) {
      console.log('[Voice] Already recording');
      return;
    }

    // Initialize WebSocket if not connected (with retry limit)
    const connected = await this.initWebSocket();
    
    if (!connected) {
      console.error('[Voice] Cannot start recording - WebSocket unavailable');
      return;
    }

    try {
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      console.log('[Voice] Microphone access granted');

      // Create MediaRecorder
      this.mediaRecorder = new MediaRecorder(stream);
      this.audioChunks = [];

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      };

      this.mediaRecorder.onstop = async () => {
        console.log('[Voice] Recording stopped, processing...');
        this.isRecording = false;
        this.onStateChange('thinking');

        // Stop all tracks to release microphone
        stream.getTracks().forEach(track => track.stop());

        // Send audio to backend for transcription
        await this.sendAudioForTranscription();
      };

      // Start recording
      this.mediaRecorder.start();
      this.isRecording = true;
      this.onStateChange('listening');
      console.log('[Voice] Recording started (5 seconds)');

      // Stop after exactly 5 seconds
      setTimeout(() => {
        if (this.mediaRecorder && this.isRecording) {
          this.mediaRecorder.stop();
          console.log('[Voice] Recording auto-stopped after 5 seconds');
        }
      }, 5000);

    } catch (err) {
      console.error('[Voice] Failed to start recording:', err);
      this.onStateChange('idle');
      alert('Please allow microphone access to use voice features.');
    }
  }

  private async sendAudioForTranscription() {
    try {
      const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
      console.log('[Voice] Audio blob size:', audioBlob.size, 'bytes');

      if (audioBlob.size === 0) {
        console.log('[Voice] No audio recorded');
        this.onStateChange('idle');
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
        // Add user message to chat
        if ((window as any).addUserMessage) {
          (window as any).addUserMessage(data.text);
        }
        // Send transcribed text via WebSocket
        this.ws?.send(JSON.stringify({
          type: 'voice_command',
          text: data.text
        }));
      } else {
        console.log('[Voice] No speech detected');
        this.onStateChange('idle');
      }

    } catch (error) {
      console.error('[Voice] Transcription error:', error);
      this.onStateChange('idle');
    }

    this.audioChunks = [];
  }

  private speak(text: string) {
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
  }

  // Backwards compatibility
  public manualWake() {
    this.startRecording();
  }

  public stop() {
    if (this.mediaRecorder && this.isRecording) {
      this.mediaRecorder.stop();
    }
    if (this.ws) {
      this.ws.close();
    }
  }
}
