import { useState, useEffect, useRef, useCallback } from 'react';
import type { WebSocketMessage } from '../types';

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

const MAX_RECONNECT_ATTEMPTS = 3;
const RECONNECT_DELAY = 5000;
const INITIAL_DELAY = 10000; // 10 seconds delay before first connection

let _initLogFired = false;

export function useWebSocket() {
  const [connected, setConnected] = useState(false);
  const [offline, setOffline] = useState(false);
  const [connecting, setConnecting] = useState(false); // New: initial delay period
  const [messages, setMessages] = useState<WebSocketMessage[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const intentionallyClosedRef = useRef(false);
  const isConnectingRef = useRef(false); // Prevent duplicate connection attempts
  const initialDelayCompleteRef = useRef(false);

  const connect = useCallback(() => {
    // Prevent duplicate connections
    if (wsRef.current?.readyState === WebSocket.OPEN || wsRef.current?.readyState === WebSocket.CONNECTING) {
      console.log('[WebSocket] Already connected or connecting, skipping');
      return;
    }

    // Prevent concurrent connection attempts
    if (isConnectingRef.current) {
      console.log('[WebSocket] Connection already in progress, skipping');
      return;
    }

    isConnectingRef.current = true;

    // Reset offline state if we're trying to reconnect
    if (offline) {
      setOffline(false);
      reconnectAttemptsRef.current = 0;
    }

    const wsUrl = getWebSocketUrl();
    const isRemote = wsUrl.startsWith('wss://');
    
    console.log(`[WebSocket] Connection attempt ${reconnectAttemptsRef.current + 1}/${MAX_RECONNECT_ATTEMPTS} to ${wsUrl}`);

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        // Log connection type for debugging
        if (isRemote) {
          console.log('[WebSocket] Connected to JARVIS via remote ngrok (wss)');
        } else {
          console.log('[WebSocket] Connected to JARVIS locally (ws)');
        }
        setConnected(true);
        setConnecting(false);
        setOffline(false);
        reconnectAttemptsRef.current = 0;
        isConnectingRef.current = false;
      };

      ws.onmessage = (event) => {
        try {
          const data: WebSocketMessage = JSON.parse(event.data);
          setMessages(prev => [...prev, data]);
        } catch (e) {
          console.error('[WebSocket] Failed to parse message:', e);
        }
      };

      ws.onerror = (error) => {
        console.error('[WebSocket] Error:', error);
        isConnectingRef.current = false;
      };

      ws.onclose = () => {
        console.log('[WebSocket] Closed');
        setConnected(false);
        isConnectingRef.current = false;
        wsRef.current = null;

        if (intentionallyClosedRef.current) {
          return;
        }

        reconnectAttemptsRef.current++;

        if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
          console.error('[WebSocket] Max reconnection attempts reached');
          setOffline(true);
          setConnecting(false);
          return;
        }

        console.log(`[WebSocket] Retrying in ${RECONNECT_DELAY / 1000}s...`);
        setTimeout(() => {
          if (!intentionallyClosedRef.current) {
            connect();
          }
        }, RECONNECT_DELAY);
      };
    } catch (error) {
      console.error('[WebSocket] Failed to create connection:', error);
      isConnectingRef.current = false;
    }
  }, [offline]);

  const disconnect = useCallback(() => {
    intentionallyClosedRef.current = true;
    wsRef.current?.close();
    wsRef.current = null;
    setConnected(false);
    setConnecting(false);
  }, []);

  const sendMessage = useCallback((message: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
      return true;
    }
    return false;
  }, []);

  // Initial 10 second delay before first connection
  useEffect(() => {
    if (!_initLogFired) {
      _initLogFired = true;
      console.log(`[WebSocket] Waiting ${INITIAL_DELAY / 1000}s before first connection...`);
    }
    setConnecting(true);

    const timer = setTimeout(() => {
      console.log('[WebSocket] Initial delay complete, ready to connect');
      initialDelayCompleteRef.current = true;
      // Don't auto-connect here - let the component call connect()
    }, INITIAL_DELAY);

    return () => {
      clearTimeout(timer);
    };
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      intentionallyClosedRef.current = true;
      wsRef.current?.close();
    };
  }, []);

  return {
    connected,
    offline,
    connecting,
    messages,
    connect,
    disconnect,
    sendMessage,
    ws: wsRef.current
  };
}
