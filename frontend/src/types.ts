/**
 * Core type definitions for JARVIS Operator
 */

// Voice state management
export type VoiceState = 'idle' | 'hotword' | 'listening' | 'thinking' | 'speaking' | 'error' | 'offline';

// WebSocket message types - comprehensive union for all message variants
export type WebSocketMessageType = 
  | 'state' 
  | 'response' 
  | 'error' 
  | 'transcription' 
  | 'ping' 
  | 'ack'
  | 'tts_done'
  | 'tts_fallback'
  | 'proactive_alert'
  | 'wake_word'
  | 'voice_command'
  | 'command'
  | 'wake_telemetry'
  | 'wake_diagnostics'
  | 'gaming_mode'
  | 'connectivity';

export interface WebSocketMessage {
  type: WebSocketMessageType;
  state?: VoiceState;
  text?: string;
  error?: string;
  model?: string;
  server_tts?: boolean;
  reason?: string;
  project?: string;
  detail?: string;
  mode?: string;
  telemetry?: Record<string, unknown>;
  online?: boolean;
  event?: string;
  active?: boolean;
}

// Conversation history entry
export interface ConversationEntry {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: number;
}

// System vitals
export interface SystemVitals {
  cpu: number;
  ram: number;
  disk: number;
  temp?: number;
  uptime?: string;
}

// Skill definition
export interface Skill {
  name: string;
  triggers: string[];
  handler: string;
  description: string;
}

// Project structure
export interface Project {
  id: string;
  name: string;
  path: string;
  type: 'web' | 'mobile' | 'desktop' | 'api' | 'other';
  status: 'active' | 'inactive' | 'error' | 'fixing';
  lastAccessed?: Date;
}

// Error entry from database
export interface ErrorEntry {
  id: number;
  project: string;
  file: string;
  line: number;
  message: string;
  timestamp: string;
  fixed: boolean;
}

// API error shape used in the dashboard flow.
export interface ErrorItem {
  id: number;
  timestamp: string;
  project_name: string;
  file_path?: string;
  error_text: string;
  suggested_fix?: string;
  severity?: 'low' | 'medium' | 'high';
  fixed?: boolean;
}
