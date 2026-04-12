import React from 'react';
import { SystemVitals } from '../SystemVitals';

interface Project {
  id: string;
  name: string;
  status: 'healthy' | 'error' | 'fixing' | 'offline';
  lastError?: string;
}

interface ErrorItem {
  id: number;
  project_name: string;
  error_text: string;
  severity: 'low' | 'medium' | 'high';
}

interface DashboardViewProps {
  vitals: {
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
  };
  projects: Project[];
  recentErrors: ErrorItem[];
}

const StatusOrb: React.FC<{ status: Project['status'] }> = ({ status }) => {
  const colors = {
    healthy: '#10b981',
    error: '#ef4444',
    fixing: '#f59e0b',
    offline: '#6b7280'
  };

  const color = colors[status];

  return (
    <div className="status-orb-wrapper">
      <div 
        className={`status-orb ${status}`}
        style={{ 
          background: color,
          boxShadow: `0 0 15px ${color}60`
        }}
      />
      {status === 'fixing' && (
        <div className="fixing-ring" style={{ borderColor: color }} />
      )}

      <style>{`
        .status-orb-wrapper {
          position: relative;
          width: 12px;
          height: 12px;
        }

        .status-orb {
          width: 100%;
          height: 100%;
          border-radius: 50%;
          transition: all 0.3s ease;
        }

        .status-orb.healthy {
          animation: healthyPulse 2s ease-in-out infinite;
        }

        @keyframes healthyPulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.1); opacity: 0.8; }
        }

        .fixing-ring {
          position: absolute;
          inset: -4px;
          border: 2px solid;
          border-radius: 50%;
          animation: spin 1s linear infinite;
          border-top-color: transparent;
        }

        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

export const DashboardView: React.FC<DashboardViewProps> = ({
  vitals,
  projects,
  recentErrors
}) => {
  const healthyCount = projects.filter(p => p.status === 'healthy').length;
  const errorCount = projects.filter(p => p.status === 'error').length;
  const fixingCount = projects.filter(p => p.status === 'fixing').length;

  return (
    <div className="dashboard-view">
      {/* Welcome Section */}
      <div className="welcome-section">
        <h1>Welcome back, <span className="highlight">RED</span></h1>
        <p className="subtitle">System Guardian is monitoring {projects.length} projects</p>
      </div>

      {/* Quick Stats Row */}
      <div className="stats-row">
        <div className="stat-card">
          <div className="stat-icon healthy">
            <span style={{ fontSize: '1.2rem' }}>✓</span>
          </div>
          <div className="stat-info">
            <span className="stat-value" style={{ color: '#10b981' }}>{healthyCount}</span>
            <span className="stat-label">Healthy</span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon fixing">
            <span style={{ fontSize: '1.2rem' }}>⚡</span>
          </div>
          <div className="stat-info">
            <span className="stat-value" style={{ color: '#f59e0b' }}>{fixingCount}</span>
            <span className="stat-label">Fixing</span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon error">
            <span style={{ fontSize: '1.2rem' }}>⚠</span>
          </div>
          <div className="stat-info">
            <span className="stat-value" style={{ color: '#ef4444' }}>{errorCount}</span>
            <span className="stat-label">Errors</span>
          </div>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="dashboard-grid">
        {/* Left Column: System Vitals */}
        <div className="grid-left">
          <SystemVitals {...vitals} />
        </div>

        {/* Right Column: Projects & Errors */}
        <div className="grid-right">
          {/* Projects Panel */}
          <div className="panel">
            <div className="panel-header">
              <span style={{ fontSize: '1rem' }}>📁</span>
              <span>Active Projects</span>
            </div>
            <div className="project-list">
              {projects.map(project => (
                <div key={project.id} className="project-item">
                  <StatusOrb status={project.status} />
                  <div className="project-info">
                    <span className="project-name">{project.name}</span>
                    {project.lastError && (
                      <span className="project-error">{project.lastError.substring(0, 50)}...</span>
                    )}
                  </div>
                  <span className={`project-status ${project.status}`}>
                    {project.status.toUpperCase()}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Recent Errors Panel */}
          {recentErrors.length > 0 && (
            <div className="panel error-panel">
              <div className="panel-header">
                <span style={{ fontSize: '1rem' }}>⚠️</span>
                <span>Recent Errors</span>
              </div>
              <div className="error-list">
                {recentErrors.slice(0, 3).map(error => (
                  <div key={error.id} className={`error-item ${error.severity}`}>
                    <div className="error-project-tag">{error.project_name}</div>
                    <div className="error-text">{error.error_text.substring(0, 60)}...</div>
                    <button className="fix-btn">Fix with AI</button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <style>{`
        .dashboard-view {
          padding: 1.5rem;
          display: flex;
          flex-direction: column;
          gap: 1.5rem;
          overflow-y: auto;
        }

        .welcome-section h1 {
          font-size: 1.5rem;
          font-weight: 600;
          color: rgba(255, 255, 255, 0.9);
          margin-bottom: 0.25rem;
        }

        .welcome-section .highlight {
          color: #00d4ff;
          text-shadow: 0 0 10px rgba(0, 212, 255, 0.3);
        }

        .subtitle {
          font-size: 0.9rem;
          color: rgba(255, 255, 255, 0.5);
        }

        .stats-row {
          display: flex;
          gap: 1rem;
        }

        .stat-card {
          flex: 1;
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 1rem;
          background: rgba(10, 10, 18, 0.6);
          border: 1px solid rgba(0, 212, 255, 0.1);
          border-radius: 10px;
        }

        .stat-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 40px;
          height: 40px;
          border-radius: 8px;
        }

        .stat-icon.healthy {
          background: rgba(16, 185, 129, 0.15);
          color: #10b981;
        }

        .stat-icon.fixing {
          background: rgba(245, 158, 11, 0.15);
          color: #f59e0b;
        }

        .stat-icon.error {
          background: rgba(239, 68, 68, 0.15);
          color: #ef4444;
        }

        .stat-info {
          display: flex;
          flex-direction: column;
        }

        .stat-value {
          font-family: 'JetBrains Mono', monospace;
          font-size: 1.5rem;
          font-weight: 700;
        }

        .stat-label {
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.5);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }

        .dashboard-grid {
          display: grid;
          grid-template-columns: 320px 1fr;
          gap: 1.5rem;
        }

        .grid-right {
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }

        .panel {
          background: rgba(10, 10, 18, 0.6);
          border: 1px solid rgba(0, 212, 255, 0.1);
          border-radius: 12px;
          overflow: hidden;
        }

        .panel.error-panel {
          border-color: rgba(239, 68, 68, 0.2);
        }

        .panel-header {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.875rem 1rem;
          background: rgba(0, 0, 0, 0.2);
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          font-size: 0.9rem;
          font-weight: 500;
          color: rgba(255, 255, 255, 0.8);
        }

        .project-list {
          display: flex;
          flex-direction: column;
        }

        .project-item {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 0.875rem 1rem;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          transition: background 0.2s ease;
        }

        .project-item:last-child {
          border-bottom: none;
        }

        .project-item:hover {
          background: rgba(255, 255, 255, 0.03);
        }

        .project-info {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }

        .project-name {
          font-size: 0.9rem;
          font-weight: 500;
          color: rgba(255, 255, 255, 0.9);
        }

        .project-error {
          font-size: 0.75rem;
          color: rgba(239, 68, 68, 0.8);
          font-family: 'JetBrains Mono', monospace;
        }

        .project-status {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.7rem;
          padding: 0.25rem 0.5rem;
          border-radius: 4px;
          font-weight: 600;
        }

        .project-status.healthy {
          background: rgba(16, 185, 129, 0.15);
          color: #10b981;
        }

        .project-status.error {
          background: rgba(239, 68, 68, 0.15);
          color: #ef4444;
        }

        .project-status.fixing {
          background: rgba(245, 158, 11, 0.15);
          color: #f59e0b;
        }

        .project-status.offline {
          background: rgba(107, 114, 128, 0.15);
          color: #6b7280;
        }

        .error-list {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
          padding: 0.75rem;
        }

        .error-item {
          padding: 0.75rem;
          background: rgba(239, 68, 68, 0.05);
          border: 1px solid rgba(239, 68, 68, 0.2);
          border-radius: 8px;
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }

        .error-item.high {
          border-left: 3px solid #ef4444;
        }

        .error-item.medium {
          border-left: 3px solid #f59e0b;
        }

        .error-item.low {
          border-left: 3px solid #10b981;
        }

        .error-project-tag {
          font-size: 0.7rem;
          color: rgba(255, 255, 255, 0.5);
          background: rgba(255, 255, 255, 0.1);
          padding: 0.2rem 0.5rem;
          border-radius: 4px;
          align-self: flex-start;
        }

        .error-text {
          font-size: 0.85rem;
          color: rgba(255, 255, 255, 0.7);
          font-family: 'JetBrains Mono', monospace;
          line-height: 1.4;
        }

        .fix-btn {
          align-self: flex-start;
          padding: 0.4rem 0.75rem;
          background: rgba(0, 212, 255, 0.15);
          border: 1px solid rgba(0, 212, 255, 0.3);
          color: #00d4ff;
          font-size: 0.75rem;
          font-family: 'JetBrains Mono', monospace;
          border-radius: 4px;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .fix-btn:hover {
          background: rgba(0, 212, 255, 0.25);
          box-shadow: 0 0 10px rgba(0, 212, 255, 0.3);
        }
      `}</style>
    </div>
  );
};
