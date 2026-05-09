/**
 * Dynamic URL resolution for JARVIS services.
 * Automatically handles local development, Ngrok tunnels, Tailscale, and custom ports.
 */

export function getApiBaseUrl(): string {
  const configured = import.meta.env.VITE_OPERATOR_API_URL as string | undefined;
  if (configured && configured.trim()) {
    return configured.trim().replace(/\/$/, '');
  }

  const host = window.location.host;
  const hostname = window.location.hostname;

  // Handle Ngrok
  if (host.includes('.ngrok-free.app') || host.includes('.ngrok-free.dev')) {
    return `${window.location.protocol}//${host}`;
  }

  // If we are NOT on localhost, assume we want to talk to the same host that served the page
  if (hostname !== 'localhost' && hostname !== '127.0.0.1') {
    return `${window.location.protocol}//${hostname}:5050`;
  }

  // Fallback to default local port
  return 'http://localhost:5050';
}

export function getWebSocketUrl(): string {
  const configured = import.meta.env.VITE_OPERATOR_WS_URL as string | undefined;
  if (configured && configured.trim()) {
    return configured.trim();
  }

  const host = window.location.host;
  const hostname = window.location.hostname;

  // Handle Ngrok WebSocket resolution
  if (host.includes('.ngrok-free.app') || host.includes('.ngrok-free.dev')) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${host}/ws`;
  }

  // If we are NOT on localhost, use the current hostname for WS
  if (hostname !== 'localhost' && hostname !== '127.0.0.1') {
    return `ws://${hostname}:8765`;
  }

  // Fallback to default local WebSocket port
  return 'ws://localhost:8765';
}

export function getVoiceServiceUrl(): string {
  const hostname = window.location.hostname;

  if (hostname !== 'localhost' && hostname !== '127.0.0.1') {
    return `ws://${hostname}:8766`;
  }

  return 'ws://localhost:8766';
}
