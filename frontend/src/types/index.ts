export interface SystemVitals {
  cpu: number;
  memory: number;
  gpu?: number;
  storage: {
    ssd: number;
    hdd: number;
  };
  temperatures: {
    cpu?: number;
    gpu?: number;
  };
}

export interface Project {
  id: string;
  name: string;
  status: 'healthy' | 'error' | 'fixing' | 'offline';
  lastError?: string;
  path: string;
  lastLaunched?: string;
}

export interface ErrorItem {
  id: number;
  timestamp: string;
  project_name: string;
  error_text: string;
  suggested_fix: string;
  severity: 'low' | 'medium' | 'high';
  fixed: boolean;
}

export interface ChatMessage {
  id: number;
  type: 'user' | 'jarvis';
  text: string;
  timestamp: Date;
  command?: string;
}

export interface ServiceStatus {
  api: boolean;
  websocket: boolean;
  ollama: boolean;
}

export interface WebSocketMessage {
  type: 'response' | 'state' | 'ack' | 'stream_chunk' | 'error';
  text?: string;
  state?: 'idle' | 'listening' | 'thinking' | 'speaking';
  message?: string;
  chunk?: string;
  partial?: string;
}

export type OrbState = 'idle' | 'listening' | 'thinking' | 'speaking';
