/**
 * Core type definitions for JARVIS Operator
 */

// Voice state management
export type VoiceState = 'idle' | 'hotword' | 'listening' | 'thinking' | 'speaking' | 'error' | 'offline';

// WebSocket message types
export interface WebSocketMessage {
  type: 'state' | 'response' | 'error' | 'transcription' | 'ping' | 'ack';
  state?: VoiceState;
  text?: string;
  error?: string;
  model?: string;
  server_tts?: boolean;
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
