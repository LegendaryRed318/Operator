import React from 'react';

interface SystemVitalsProps {
  cpu: number;
  memory: number;
  tempCPU?: number | null;
  tempGPU?: number | null;
  hasTemperatures?: boolean;
  ramUsedGB?: number;
  ramTotalGB?: number;
  // Drive C: Windows
  diskCPercent?: number;
  diskCLabel?: string;
  diskCUsedGB?: number;
  diskCTotalGB?: number;
  // Drive D: Micro SSD
  diskDPercent?: number;
  diskDLabel?: string;
  diskDUsedGB?: number;
  diskDTotalGB?: number;
  // Drive E: HDD
  diskEPercent?: number;
  diskELabel?: string;
  diskEUsedGB?: number;
  diskETotalGB?: number;
}

// CSS-only circular progress component
const CircularGauge: React.FC<{
  value: number;
  max?: number;
  size?: number;
  strokeWidth?: number;
  color: string;
  icon: React.ReactNode;
  label: string;
  sublabel?: string;
}> = ({ value, max = 100, size = 100, strokeWidth = 8, color, icon, label, sublabel }) => {
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const progress = Math.min(value / max, 1);
  const dashoffset = circumference - progress * circumference;

  // Determine color based on value
  const getColor = () => {
    if (value > 85) return '#ef4444'; // Red for danger
    if (value > 60) return '#f59e0b'; // Orange for warning
    return color;
  };

  const finalColor = getColor();

  return (
    <div className="gauge-container">
      <div className="gauge-svg-wrapper" style={{ width: size, height: size }}>
        <svg className="gauge-svg" width={size} height={size}>
          {/* Background circle */}
          <circle
            className="gauge-bg"
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            strokeWidth={strokeWidth}
          />
          {/* Progress circle */}
          <circle
            className="gauge-progress"
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={finalColor}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={dashoffset}
            strokeLinecap="round"
            style={{
              filter: `drop-shadow(0 0 6px ${finalColor}40)`,
              transition: 'stroke-dashoffset 0.5s ease, stroke 0.3s ease'
            }}
          />
        </svg>
        {/* Center content */}
        <div className="gauge-center">
          <div className="gauge-icon" style={{ color: finalColor }}>
            {icon}
          </div>
          <div className="gauge-value" style={{ color: finalColor }}>
            {Math.round(value)}%
          </div>
        </div>
      </div>
      <div className="gauge-label">{label}</div>
      {sublabel && <div className="gauge-sublabel">{sublabel}</div>}

      <style>{`
        .gauge-container {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 0.5rem;
        }

        .gauge-svg-wrapper {
          position: relative;
          transform: rotate(-90deg);
        }

        .gauge-svg {
          overflow: visible;
        }

        .gauge-bg {
          stroke: rgba(255, 255, 255, 0.1);
        }

        .gauge-center {
          position: absolute;
          inset: 0;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          transform: rotate(90deg);
          gap: 2px;
        }

        .gauge-icon {
          opacity: 0.8;
        }

        .gauge-value {
          font-family: 'JetBrains Mono', monospace;
          font-size: 1.1rem;
          font-weight: 700;
        }

        .gauge-label {
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.7);
          font-weight: 500;
        }

        .gauge-sublabel {
          font-size: 0.7rem;
          color: rgba(255, 255, 255, 0.4);
          font-family: 'JetBrains Mono', monospace;
        }
      `}</style>
    </div>
  );
};

// Linear progress bar for storage
const StorageBar: React.FC<{
  label: string;
  used: number;
  total: string;
  color: string;
}> = ({ label, used, total, color }) => (
  <div className="storage-bar">
    <div className="storage-header">
      <div className="storage-label">
        <span style={{ fontSize: '0.9rem', color }}>💾</span>
        <span>{label}</span>
      </div>
      <span className="storage-value" style={{ color }}>{used}%</span>
    </div>
    <div className="storage-track">
      <div 
        className="storage-fill"
        style={{ 
          width: `${used}%`,
          background: `linear-gradient(90deg, ${color}80, ${color})`,
          boxShadow: `0 0 10px ${color}40`
        }}
      />
    </div>
    <div className="storage-total">{total}</div>

    <style>{`
      .storage-bar {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
      }

      .storage-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }

      .storage-label {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.85rem;
        color: rgba(255, 255, 255, 0.8);
      }

      .storage-value {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.9rem;
        font-weight: 600;
      }

      .storage-track {
        height: 6px;
        background: rgba(255, 255, 255, 0.1);
        border-radius: 3px;
        overflow: hidden;
      }

      .storage-fill {
        height: 100%;
        border-radius: 3px;
        transition: width 0.5s ease;
      }

      .storage-total {
        font-size: 0.75rem;
        color: rgba(255, 255, 255, 0.4);
        font-family: 'JetBrains Mono', monospace;
      }
    `}</style>
  </div>
);

// Temperature indicator
const TempIndicator: React.FC<{
  label: string;
  temp: number | null;
}> = ({ label, temp }) => {
  const getColor = () => {
    if (temp === null) return '#666';
    if (temp > 80) return '#ef4444';
    if (temp > 65) return '#f59e0b';
    return '#00d4ff';
  };

  const color = getColor();

  return (
    <div className="temp-indicator">
      <span style={{ fontSize: '0.9rem', color }}>🌡️</span>
      <div className="temp-info">
        <span className="temp-label">{label}</span>
        <span className="temp-value" style={{ color }}>
          {temp !== null ? `${temp}°C` : '--'}
        </span>
      </div>

      <style>{`
        .temp-indicator {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.5rem 0.75rem;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 6px;
        }

        .temp-info {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }

        .temp-label {
          font-size: 0.7rem;
          color: rgba(255, 255, 255, 0.5);
        }

        .temp-value {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.85rem;
          font-weight: 600;
        }
      `}</style>
    </div>
  );
};

export const SystemVitals: React.FC<SystemVitalsProps> = ({
  cpu,
  memory,
  tempCPU,
  tempGPU,
  hasTemperatures,
  ramUsedGB,
  ramTotalGB,
  diskCPercent,
  diskCLabel,
  diskCUsedGB,
  diskCTotalGB,
  diskDPercent,
  diskDLabel,
  diskDUsedGB,
  diskDTotalGB,
  diskEPercent,
  diskELabel,
  diskEUsedGB,
  diskETotalGB,
}) => {
  return (
    <div className="system-vitals">
      <div className="vitals-header">
        <h2>System Vitals</h2>
        <div className="live-indicator">
          <span className="live-dot"></span>
          <span>LIVE</span>
        </div>
      </div>

      <div className="vitals-grid">
        {/* Main Gauges */}
        <div className="gauges-row">
          <CircularGauge
            value={cpu}
            color="#00d4ff"
            icon={<span style={{ fontSize: '0.9rem' }}>🖥️</span>}
            label="CPU"
            sublabel="8-Core AMD"
          />
          <CircularGauge
            value={memory}
            color="#8b5cf6"
            icon={<span style={{ fontSize: '0.9rem' }}>RAM</span>}
            label="Memory"
            sublabel={ramTotalGB ? `${ramUsedGB?.toFixed(1)} / ${ramTotalGB.toFixed(1)} GB` : 'Loading...'}
          />
        </div>

        {/* Storage Section */}
        <div className="storage-section">
          {diskCPercent !== undefined && (
            <StorageBar
              label={diskCLabel || "Windows (C:)"}
              used={diskCPercent}
              total={`${diskCUsedGB}GB / ${diskCTotalGB}GB`}
              color="#00d4ff"
            />
          )}
          {diskDPercent !== undefined && (
            <StorageBar
              label={diskDLabel || "Micro SSD (D:)"}
              used={diskDPercent}
              total={`${diskDUsedGB}GB / ${diskDTotalGB}GB`}
              color="#8b5cf6"
            />
          )}
          {diskEPercent !== undefined && (
            <StorageBar
              label={diskELabel || "HDD (E:)"}
              used={diskEPercent}
              total={`${diskEUsedGB}GB / ${diskETotalGB}GB`}
              color="#f59e0b"
            />
          )}
        </div>

        {/* Temperature Section - only show if hasTemperatures is true */}
        {hasTemperatures && (tempCPU !== undefined && tempCPU !== null || tempGPU !== undefined && tempGPU !== null) && (
          <div className="temp-section">
            {tempCPU !== undefined && tempCPU !== null && (
              <TempIndicator label="CPU Temp" temp={tempCPU} />
            )}
            {tempGPU !== undefined && tempGPU !== null && (
              <TempIndicator label="GPU Temp" temp={tempGPU} />
            )}
          </div>
        )}
      </div>

      <style>{`
        .system-vitals {
          background: rgba(10, 10, 18, 0.6);
          border: 1px solid rgba(0, 212, 255, 0.1);
          border-radius: 12px;
          padding: 1.5rem;
        }

        .vitals-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1.5rem;
        }

        .vitals-header h2 {
          font-size: 1rem;
          font-weight: 600;
          color: rgba(255, 255, 255, 0.9);
          letter-spacing: 0.05em;
        }

        .live-indicator {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.75rem;
          color: #10b981;
          letter-spacing: 0.1em;
        }

        .live-dot {
          width: 6px;
          height: 6px;
          background: #10b981;
          border-radius: 50%;
          box-shadow: 0 0 8px #10b981;
          animation: pulse 2s ease-in-out infinite;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }

        .vitals-grid {
          display: flex;
          flex-direction: column;
          gap: 1.5rem;
        }

        .gauges-row {
          display: flex;
          justify-content: space-around;
          gap: 1rem;
        }

        .storage-section {
          display: flex;
          flex-direction: column;
          gap: 1rem;
          padding-top: 1rem;
          border-top: 1px solid rgba(255, 255, 255, 0.05);
        }

        .temp-section {
          display: flex;
          gap: 1rem;
          flex-wrap: wrap;
        }
      `}</style>
    </div>
  );
};
