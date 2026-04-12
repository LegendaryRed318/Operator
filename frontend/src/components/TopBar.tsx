import React from 'react';

interface TopBarProps {
  wsConnected: boolean;
  wsOffline: boolean;
  wsConnecting: boolean;
  apiConnected: boolean;
  ollamaConnected: boolean;
  activeModel: string;
  clientCount: number;
}

export const TopBar: React.FC<TopBarProps> = ({
  wsConnected,
  wsOffline,
  wsConnecting,
  apiConnected,
  ollamaConnected,
  activeModel,
  clientCount
}) => {
  return (
    <header className="topbar">
      {/* Left: Command Palette Hint */}
      <div className="topbar-left">
        <div className="command-hint">
          <span style={{ fontSize: '0.9rem' }}>⌘</span>
          <span>Ctrl+K</span>
        </div>
      </div>

      {/* Center: Status Pills */}
      <div className="topbar-center">
        {/* Jarvis Status */}
        <div className={`status-pill ${wsOffline ? 'offline' : wsConnected ? 'online' : wsConnecting ? 'connecting' : 'idle'}`}>
          {wsOffline ? (
            <>
              <span style={{ fontSize: '0.9rem' }}>📡❌</span>
              <span>JARVIS OFFLINE</span>
            </>
          ) : wsConnected ? (
            <>
              <span style={{ fontSize: '0.9rem' }}>📡</span>
              <span>JARVIS ONLINE</span>
            </>
          ) : wsConnecting ? (
            <>
              <span className="connecting-dot"></span>
              <span>CONNECTING TO JARVIS...</span>
            </>
          ) : (
            <>
              <span style={{ fontSize: '0.9rem' }}>○</span>
              <span>JARVIS IDLE</span>
            </>
          )}
        </div>

        {/* Model Badge */}
        <div className="model-badge">
          <span style={{ fontSize: '0.9rem' }}>🧠</span>
          <span>{activeModel}</span>
        </div>
      </div>

      {/* Right: Service Indicators */}
      <div className="topbar-right">
        {/* API Server */}
        <div className="service-indicator" title="API Server">
          <span className={apiConnected ? 'online' : 'offline'} style={{ fontSize: '0.9rem' }}>🖥️</span>
        </div>

        {/* Ollama */}
        <div className="service-indicator" title="Ollama">
          <span className={ollamaConnected ? 'online' : 'offline'} style={{ fontSize: '0.9rem' }}>🧠</span>
        </div>

        {/* Connected Clients */}
        <div className="clients-badge">
          <span style={{ fontSize: '0.9rem' }}>👤</span>
          <span>{clientCount}</span>
        </div>
      </div>

      <style>{`
        .topbar {
          height: 56px;
          background: rgba(5, 5, 8, 0.8);
          backdrop-filter: blur(12px);
          border-bottom: 1px solid rgba(0, 212, 255, 0.1);
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 1.5rem;
          position: sticky;
          top: 0;
          z-index: 50;
        }

        .topbar-left {
          display: flex;
          align-items: center;
        }

        .command-hint {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.4rem 0.75rem;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 6px;
          color: rgba(255, 255, 255, 0.5);
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.8rem;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .command-hint:hover {
          background: rgba(0, 212, 255, 0.1);
          color: rgba(255, 255, 255, 0.8);
        }

        .topbar-center {
          display: flex;
          align-items: center;
          gap: 1rem;
          position: absolute;
          left: 50%;
          transform: translateX(-50%);
        }

        .status-pill {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.5rem 1rem;
          border-radius: 20px;
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.8rem;
          font-weight: 600;
          letter-spacing: 0.05em;
          transition: all 0.3s ease;
        }

        .status-pill.online {
          background: rgba(16, 185, 129, 0.15);
          color: #10b981;
          border: 1px solid rgba(16, 185, 129, 0.3);
          box-shadow: 0 0 10px rgba(16, 185, 129, 0.2);
        }

        .status-pill.offline {
          background: rgba(239, 68, 68, 0.15);
          color: #ef4444;
          border: 1px solid rgba(239, 68, 68, 0.3);
          box-shadow: 0 0 10px rgba(239, 68, 68, 0.2);
          animation: pulseRed 2s ease-in-out infinite;
        }

        @keyframes pulseRed {
          0%, 100% { box-shadow: 0 0 10px rgba(239, 68, 68, 0.2); }
          50% { box-shadow: 0 0 20px rgba(239, 68, 68, 0.4); }
        }

        .status-pill.connecting {
          background: rgba(245, 158, 11, 0.15);
          color: #f59e0b;
          border: 1px solid rgba(245, 158, 11, 0.3);
        }

        .connecting-dot {
          width: 8px;
          height: 8px;
          background: #f59e0b;
          border-radius: 50%;
          animation: blink 1s ease-in-out infinite;
        }

        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }

        .model-badge {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.4rem 0.75rem;
          background: rgba(139, 92, 246, 0.15);
          border: 1px solid rgba(139, 92, 246, 0.3);
          border-radius: 16px;
          color: #8b5cf6;
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.75rem;
        }

        .topbar-right {
          display: flex;
          align-items: center;
          gap: 1rem;
        }

        .service-indicator {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 28px;
          height: 28px;
          border-radius: 6px;
          background: rgba(255, 255, 255, 0.05);
          transition: all 0.2s ease;
        }

        .service-indicator .online {
          color: #10b981;
          filter: drop-shadow(0 0 4px #10b981);
        }

        .service-indicator .offline {
          color: #ef4444;
          filter: drop-shadow(0 0 4px #ef4444);
        }

        .clients-badge {
          display: flex;
          align-items: center;
          gap: 0.4rem;
          padding: 0.4rem 0.6rem;
          background: rgba(0, 212, 255, 0.1);
          border: 1px solid rgba(0, 212, 255, 0.2);
          border-radius: 6px;
          color: #00d4ff;
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.8rem;
        }
      `}</style>
    </header>
  );
};
