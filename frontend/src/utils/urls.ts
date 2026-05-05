/**
 * Dynamic URL resolution for JARVIS services.
 * Automatically handles local development, Ngrok tunnels, Tailscale, and custom ports.
 */

// Tailscale IP range: 100.64.0.0 - 100.127.255.255 (CGNAT range)
const isTailscaleIP = (host: string): boolean => {
  // Extract IP from host:port
  const ip = host.split(':')[0];
  return /^100\.(6[4-9]|[7-9]\d|1[0-1]\d|12[0-7])\.\d{1,3}\.\d{1,3}$/.test(ip);
};

export function getApiBaseUrl(): string {
  const configured = import.meta.env.VITE_OPERATOR_API_URL as string | undefined;
  if (configured && configured.trim()) {
    return configured.trim().replace(/\/$/, '');
  }

  const host = window.location.host;
  const hostname = window.location.hostname;

  // If we are on an Ngrok domain, use the current host as the API base
  if (host.includes('.ngrok-free.app') || host.includes('.ngrok-free.dev')) {
    return `${window.location.protocol}//${host}`;
  }

  // If we're accessing via Tailscale IP, use the same host for API
  if (isTailscaleIP(hostname)) {
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

  // Handle Tailscale WebSocket
  if (isTailscaleIP(hostname)) {
    return `ws://${hostname}:8765`;
  }

  // Fallback to default local WebSocket port
  return 'ws://localhost:8765';
}
