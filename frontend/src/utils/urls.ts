/**
 * Dynamic URL resolution for JARVIS services.
 * Automatically handles local development, Ngrok tunnels, and custom ports.
 */

export function getApiBaseUrl(): string {
  const configured = import.meta.env.VITE_OPERATOR_API_URL as string | undefined;
  if (configured && configured.trim()) {
    return configured.trim().replace(/\/$/, '');
  }

  const host = window.location.host;
  // If we are on an Ngrok domain, use the current host as the API base
  if (host.includes('.ngrok-free.app') || host.includes('.ngrok-free.dev')) {
    return `${window.location.protocol}//${host}`;
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
  // Handle Ngrok WebSocket resolution
  if (host.includes('.ngrok-free.app') || host.includes('.ngrok-free.dev')) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${host}/ws`;
  }

  // Fallback to default local WebSocket port
  return 'ws://localhost:8765';
}
