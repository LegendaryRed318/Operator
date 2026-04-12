import React from 'react';

interface SystemViewProps {
  vitals: {
    cpu: number;
    memory: number;
    tempCPU: number | null;
    tempGPU: number | null;
    hasTemperatures: boolean;
    ramUsedGB: number;
    ramTotalGB: number;
    // Drive C: Windows
    diskCPercent: number;
    diskCLabel: string;
    diskCUsedGB: number;
    diskCTotalGB: number;
    // Drive D: Micro SSD
    diskDPercent: number;
    diskDLabel: string;
    diskDUsedGB: number;
    diskDTotalGB: number;
    // Drive E: HDD
    diskEPercent: number;
    diskELabel: string;
    diskEUsedGB: number;
    diskETotalGB: number;
  };
  cpuHistory: number[];
}

export const SystemView: React.FC<SystemViewProps> = ({ vitals, cpuHistory }) => {
  // SVG line graph for CPU history
  const renderCpuGraph = () => {
    const width = 600;
    const height = 150;
    const padding = 20;
    
    const data = cpuHistory;
    const maxVal = 100;
    const minVal = 0;
    
    // Calculate points
    const points = data.map((val, i) => {
      const x = padding + (i / (data.length - 1)) * (width - 2 * padding);
      const y = height - padding - ((val - minVal) / (maxVal - minVal)) * (height - 2 * padding);
      return `${x},${y}`;
    }).join(' ');

    // Grid lines
    const gridLines = [0, 25, 50, 75, 100].map(val => {
      const y = height - padding - ((val - minVal) / (maxVal - minVal)) * (height - 2 * padding);
      return (
        <g key={val}>
          <line x1={padding} y1={y} x2={width - padding} y2={y} stroke="rgba(255,255,255,0.1)" strokeDasharray="4" />
          <text x={padding - 5} y={y + 3} fill="rgba(255,255,255,0.4)" fontSize="10" textAnchor="end">{val}%</text>
        </g>
      );
    });

    return (
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        {/* Background */}
        <rect x={0} y={0} width={width} height={height} fill="rgba(0,0,0,0.3)" rx={8} />
        
        {/* Grid */}
        {gridLines}
        
        {/* Area under line */}
        <polygon 
          points={`${padding},${height - padding} ${points} ${width - padding},${height - padding}`}
          fill="url(#cpuGradient)"
          opacity="0.3"
        />
        
        {/* Line */}
        <polyline 
          points={points}
          fill="none"
          stroke="#00d4ff"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        
        {/* Current point highlight */}
        {data.length > 0 && (() => {
          const lastVal = data[data.length - 1];
          const x = width - padding;
          const y = height - padding - ((lastVal - minVal) / (maxVal - minVal)) * (height - 2 * padding);
          return (
            <g>
              <circle cx={x} cy={y} r={4} fill="#00d4ff" />
              <circle cx={x} cy={y} r={8} fill="rgba(0,212,255,0.3)" />
            </g>
          );
        })()}
        
        {/* Gradient definition */}
        <defs>
          <linearGradient id="cpuGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#00d4ff" />
            <stop offset="100%" stopColor="rgba(0,212,255,0)" />
          </linearGradient>
        </defs>
      </svg>
    );
  };

  // Circular gauge component
  const CircularGauge: React.FC<{
    value: number;
    max?: number;
    label: string;
    sublabel?: string;
    color: string;
    size?: number;
  }> = ({ value, max = 100, label, sublabel, color, size = 160 }) => {
    const radius = (size - 20) / 2;
    const circumference = 2 * Math.PI * radius;
    const strokeDashoffset = circumference - (value / max) * circumference;

    return (
      <div className="gauge-wrapper" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="gauge-svg">
          {/* Background circle */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="rgba(255,255,255,0.1)"
            strokeWidth={12}
          />
          {/* Progress circle */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={12}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            style={{ 
              transform: 'rotate(-90deg)', 
              transformOrigin: 'center',
              transition: 'stroke-dashoffset 0.5s ease'
            }}
          />
        </svg>
        <div className="gauge-content">
          <span className="gauge-value" style={{ color }}>{Math.round(value)}%</span>
          <span className="gauge-label">{label}</span>
          {sublabel && <span className="gauge-sublabel">{sublabel}</span>}
        </div>
      </div>
    );
  };

  // Storage bar component
  const StorageBar: React.FC<{
    label: string;
    used: number;
    total: number;
    usedGB: number;
    totalGB: number;
    color: string;
  }> = ({ label, used, usedGB, totalGB, color }) => (
    <div className="storage-bar">
      <div className="storage-header">
        <span className="storage-label">{label}</span>
        <span className="storage-value" style={{ color }}>
          {used}% ({Math.round(usedGB)} / {Math.round(totalGB)} GB)
        </span>
      </div>
      <div className="storage-track">
        <div 
          className="storage-fill"
          style={{ 
            width: `${used}%`,
            background: `linear-gradient(90deg, ${color}80, ${color})`
          }}
        />
      </div>
    </div>
  );

  // Temperature display
  const TempDisplay: React.FC<{
    label: string;
    temp: number | null;
    unit?: string;
  }> = ({ label, temp, unit = '°C' }) => {
    const getColor = () => {
      if (temp === null) return '#666';
      if (temp > 80) return '#ef4444';
      if (temp > 65) return '#f59e0b';
      return '#00d4ff';
    };

    return (
      <div className="temp-display">
        <span className="temp-label">{label}</span>
        <span className="temp-value" style={{ color: getColor() }}>
          {temp !== null ? `${Math.round(temp)}${unit}` : '--'}
        </span>
      </div>
    );
  };

  return (
    <div className="system-view">
      <div className="system-header">
        <h2>System Monitor</h2>
        <span className="live-indicator">
          <span className="live-dot" />
          LIVE
        </span>
      </div>

      {/* Main Gauges Row */}
      <div className="gauges-section">
        <div className="gauge-card">
          <CircularGauge
            value={vitals.cpu}
            label="CPU"
            sublabel="Usage"
            color="#00d4ff"
            size={200}
          />
          <div className="gauge-details">
            <span>Real-time processor load</span>
          </div>
        </div>

        <div className="gauge-card">
          <CircularGauge
            value={vitals.memory}
            label="RAM"
            sublabel={`${vitals.ramUsedGB.toFixed(1)} / ${vitals.ramTotalGB.toFixed(1)} GB`}
            color="#8b5cf6"
            size={200}
          />
          <div className="gauge-details">
            <span>Memory utilization</span>
          </div>
        </div>

        {/* Temperature Section - only show if hasTemperatures is true */}
        {vitals.hasTemperatures && (
          <div className="temp-card">
            <h3>Temperatures</h3>
            <TempDisplay label="CPU" temp={vitals.tempCPU} />
            <TempDisplay label="GPU" temp={vitals.tempGPU} />
          </div>
        )}
      </div>

      {/* Storage Section */}
      <div className="storage-section">
        <h3>Storage</h3>
        <div className="storage-grid">
          <div className="storage-card">
            <StorageBar
              label={vitals.diskCLabel}
              used={vitals.diskCPercent}
              total={100}
              usedGB={vitals.diskCUsedGB}
              totalGB={vitals.diskCTotalGB}
              color="#00d4ff"
            />
          </div>
          <div className="storage-card">
            <StorageBar
              label={vitals.diskDLabel}
              used={vitals.diskDPercent}
              total={100}
              usedGB={vitals.diskDUsedGB}
              totalGB={vitals.diskDTotalGB}
              color="#8b5cf6"
            />
          </div>
          <div className="storage-card">
            <StorageBar
              label={vitals.diskELabel}
              used={vitals.diskEPercent}
              total={100}
              usedGB={vitals.diskEUsedGB}
              totalGB={vitals.diskETotalGB}
              color="#f59e0b"
            />
          </div>
        </div>
      </div>

      {/* CPU History Graph */}
      <div className="graph-section">
        <div className="graph-header">
          <h3>CPU Usage History</h3>
          <span className="graph-label">Last 60 seconds</span>
        </div>
        <div className="graph-container">
          {renderCpuGraph()}
        </div>
      </div>

      <style>{`
        .system-view {
          height: 100%;
          overflow-y: auto;
          padding: 1.5rem;
          display: flex;
          flex-direction: column;
          gap: 1.5rem;
        }

        .system-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .system-header h2 {
          font-size: 1.5rem;
          font-weight: 600;
          color: rgba(255, 255, 255, 0.9);
          margin: 0;
        }

        .live-indicator {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.75rem;
          font-weight: 600;
          color: #10b981;
          background: rgba(16, 185, 129, 0.1);
          padding: 0.4rem 0.8rem;
          border-radius: 1rem;
          border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .live-dot {
          width: 6px;
          height: 6px;
          background: #10b981;
          border-radius: 50%;
          animation: pulse 2s infinite;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }

        .gauges-section {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 1.5rem;
        }

        .gauge-card, .temp-card {
          background: rgba(10, 10, 15, 0.8);
          border: 1px solid rgba(0, 212, 255, 0.15);
          border-radius: 12px;
          padding: 1.5rem;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 1rem;
        }

        .gauge-wrapper {
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .gauge-svg {
          position: absolute;
          top: 0;
          left: 0;
        }

        .gauge-content {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 0.25rem;
        }

        .gauge-value {
          font-size: 2rem;
          font-weight: 700;
        }

        .gauge-label {
          font-size: 0.9rem;
          color: rgba(255, 255, 255, 0.6);
          text-transform: uppercase;
          letter-spacing: 1px;
        }

        .gauge-sublabel {
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.4);
        }

        .gauge-details {
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.4);
          text-align: center;
        }

        .temp-card {
          min-width: 160px;
        }

        .temp-card h3 {
          font-size: 0.9rem;
          color: rgba(255, 255, 255, 0.6);
          text-transform: uppercase;
          letter-spacing: 1px;
          margin: 0 0 0.5rem 0;
        }

        .temp-display {
          display: flex;
          align-items: center;
          justify-content: space-between;
          width: 100%;
          padding: 0.75rem;
          background: rgba(255, 255, 255, 0.03);
          border-radius: 8px;
        }

        .temp-label {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.5);
        }

        .temp-value {
          font-size: 1.2rem;
          font-weight: 600;
        }

        .storage-section {
          background: rgba(10, 10, 15, 0.8);
          border: 1px solid rgba(0, 212, 255, 0.15);
          border-radius: 12px;
          padding: 1.25rem;
        }

        .storage-section h3 {
          font-size: 0.9rem;
          color: rgba(255, 255, 255, 0.6);
          text-transform: uppercase;
          letter-spacing: 1px;
          margin: 0 0 1rem 0;
        }

        .storage-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
          gap: 1rem;
        }

        .storage-card {
          padding: 1rem;
          background: rgba(255, 255, 255, 0.03);
          border-radius: 8px;
        }

        .storage-bar {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }

        .storage-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: 0.9rem;
        }

        .storage-label {
          color: rgba(255, 255, 255, 0.7);
        }

        .storage-value {
          font-weight: 600;
        }

        .storage-track {
          height: 8px;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 4px;
          overflow: hidden;
        }

        .storage-fill {
          height: 100%;
          border-radius: 4px;
          transition: width 0.5s ease;
        }

        .graph-section {
          background: rgba(10, 10, 15, 0.8);
          border: 1px solid rgba(0, 212, 255, 0.15);
          border-radius: 12px;
          padding: 1.25rem;
        }

        .graph-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 1rem;
        }

        .graph-header h3 {
          font-size: 0.9rem;
          color: rgba(255, 255, 255, 0.6);
          text-transform: uppercase;
          letter-spacing: 1px;
          margin: 0;
        }

        .graph-label {
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.4);
        }

        .graph-container {
          width: 100%;
        }
      `}</style>
    </div>
  );
};
