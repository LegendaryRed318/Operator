import React from 'react';

interface LoadingScreenProps {
  isLoading: boolean;
}

export const LoadingScreen: React.FC<LoadingScreenProps> = ({ isLoading }) => {
  if (!isLoading) return null;

  return (
    <div className="loading-screen">
      <div className="loading-content">
        <div className="loading-orb">
          <div className="orb-ring orb-ring-1"></div>
          <div className="orb-ring orb-ring-2"></div>
          <div className="orb-ring orb-ring-3"></div>
          <div className="orb-core"></div>
        </div>
        <h1 className="loading-title">INITIALIZING JARVIS...</h1>
        <div className="loading-bar">
          <div className="loading-progress"></div>
        </div>
        <p className="loading-subtitle">System Guardian Online</p>
      </div>

      <style>{`
        .loading-screen {
          position: fixed;
          inset: 0;
          background: linear-gradient(135deg, #020204 0%, #050508 50%, #0a0a12 100%);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 9999;
          animation: fadeIn 0.3s ease-out;
        }

        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }

        .loading-content {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 2rem;
        }

        .loading-orb {
          position: relative;
          width: 120px;
          height: 120px;
        }

        .orb-core {
          position: absolute;
          inset: 35px;
          background: radial-gradient(circle at 30% 30%, #00d4ff, #0088aa);
          border-radius: 50%;
          box-shadow: 
            0 0 20px rgba(0, 212, 255, 0.5),
            0 0 40px rgba(0, 212, 255, 0.3),
            0 0 60px rgba(0, 212, 255, 0.1);
          animation: pulseCore 1.5s ease-in-out infinite;
        }

        @keyframes pulseCore {
          0%, 100% {
            transform: scale(1);
            opacity: 0.8;
          }
          50% {
            transform: scale(1.1);
            opacity: 1;
          }
        }

        .orb-ring {
          position: absolute;
          inset: 0;
          border: 2px solid transparent;
          border-radius: 50%;
          border-top-color: rgba(0, 212, 255, 0.3);
          border-right-color: rgba(0, 212, 255, 0.1);
        }

        .orb-ring-1 {
          animation: spin 2s linear infinite;
        }

        .orb-ring-2 {
          inset: 10px;
          animation: spin 2.5s linear infinite reverse;
        }

        .orb-ring-3 {
          inset: 20px;
          animation: spin 3s linear infinite;
        }

        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }

        .loading-title {
          font-family: 'JetBrains Mono', 'Fira Code', monospace;
          font-size: 1.5rem;
          font-weight: 600;
          letter-spacing: 0.3em;
          color: #00d4ff;
          text-shadow: 
            0 0 10px rgba(0, 212, 255, 0.5),
            0 0 20px rgba(0, 212, 255, 0.3),
            0 0 30px rgba(0, 212, 255, 0.2);
          animation: textPulse 1.5s ease-in-out infinite;
        }

        @keyframes textPulse {
          0%, 100% { opacity: 0.7; }
          50% { opacity: 1; }
        }

        .loading-bar {
          width: 300px;
          height: 3px;
          background: rgba(0, 212, 255, 0.1);
          border-radius: 2px;
          overflow: hidden;
          position: relative;
        }

        .loading-progress {
          position: absolute;
          left: 0;
          top: 0;
          height: 100%;
          width: 40%;
          background: linear-gradient(90deg, #00d4ff, #8b5cf6);
          border-radius: 2px;
          animation: progressSlide 1.5s ease-in-out infinite;
          box-shadow: 0 0 10px rgba(0, 212, 255, 0.5);
        }

        @keyframes progressSlide {
          0% { transform: translateX(-100%); }
          50% { transform: translateX(150%); }
          100% { transform: translateX(-100%); }
        }

        .loading-subtitle {
          font-family: 'Inter', sans-serif;
          font-size: 0.875rem;
          color: rgba(0, 212, 255, 0.5);
          letter-spacing: 0.2em;
          text-transform: uppercase;
        }
      `}</style>
    </div>
  );
};
