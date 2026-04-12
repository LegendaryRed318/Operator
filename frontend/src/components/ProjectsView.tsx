import React, { useMemo } from 'react';
import type { ErrorItem } from '../types';

interface ProjectsViewProps {
  errors: ErrorItem[];
}

interface ProjectSummary {
  name: string;
  errorCount: number;
  lastErrorTime: string;
  recentErrors: ErrorItem[];
}

export const ProjectsView: React.FC<ProjectsViewProps> = ({ errors }) => {
  // Group errors by project_name
  const projects = useMemo(() => {
    const grouped = new Map<string, ErrorItem[]>();
    
    errors.forEach(error => {
      const projectName = error.project_name || 'Unknown Project';
      if (!grouped.has(projectName)) {
        grouped.set(projectName, []);
      }
      grouped.get(projectName)!.push(error);
    });
    
    // Convert to sorted array (most recent errors first)
    const summaries: ProjectSummary[] = [];
    grouped.forEach((projectErrors, name) => {
      const sorted = projectErrors.sort((a, b) => 
        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      );
      summaries.push({
        name,
        errorCount: projectErrors.length,
        lastErrorTime: sorted[0].timestamp,
        recentErrors: sorted.slice(0, 5), // Last 5 errors
      });
    });
    
    return summaries.sort((a, b) => b.errorCount - a.errorCount);
  }, [errors]);

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="projects-view">
      <div className="projects-header">
        <h2>Project Error Monitor</h2>
        <span className="project-count">{projects.length} Projects</span>
      </div>

      <div className="projects-grid">
        {projects.map(project => (
          <div key={project.name} className="project-card">
            <div className="project-card-header">
              <div className="project-title-section">
                <span className="project-icon">📁</span>
                <h3 className="project-name">{project.name}</h3>
              </div>
              <div className="project-stats">
                <span className={`error-badge ${project.errorCount > 5 ? 'high' : project.errorCount > 0 ? 'medium' : 'low'}`}>
                  {project.errorCount} Errors
                </span>
              </div>
            </div>

            <div className="project-meta">
              <span className="last-error-time">
                Last: {formatTime(project.lastErrorTime)}
              </span>
            </div>

            <div className="recent-errors">
              <h4>Recent Errors</h4>
              {project.recentErrors.map(error => (
                <div key={error.id} className={`error-row ${error.severity}`}>
                  <span className="error-severity-dot" />
                  <span className="error-text" title={error.error_text}>
                    {error.error_text.length > 60 
                      ? error.error_text.substring(0, 60) + '...' 
                      : error.error_text}
                  </span>
                </div>
              ))}
            </div>

            <button className="fix-all-btn">
              <span>🔧</span>
              Fix All with AI
            </button>
          </div>
        ))}

        {projects.length === 0 && (
          <div className="no-projects">
            <span className="no-projects-icon">✓</span>
            <p>No errors found. All projects are healthy!</p>
          </div>
        )}
      </div>

      <style>{`
        .projects-view {
          height: 100%;
          overflow-y: auto;
          padding: 1.5rem;
        }

        .projects-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 1.5rem;
        }

        .projects-header h2 {
          font-size: 1.5rem;
          font-weight: 600;
          color: rgba(255, 255, 255, 0.9);
          margin: 0;
        }

        .project-count {
          font-size: 0.9rem;
          color: rgba(255, 255, 255, 0.5);
          background: rgba(0, 212, 255, 0.1);
          padding: 0.4rem 0.8rem;
          border-radius: 1rem;
          border: 1px solid rgba(0, 212, 255, 0.2);
        }

        .projects-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
          gap: 1rem;
        }

        .project-card {
          background: rgba(10, 10, 15, 0.8);
          border: 1px solid rgba(0, 212, 255, 0.15);
          border-radius: 12px;
          padding: 1.25rem;
          display: flex;
          flex-direction: column;
          gap: 1rem;
          transition: all 0.2s ease;
        }

        .project-card:hover {
          border-color: rgba(0, 212, 255, 0.3);
          box-shadow: 0 4px 20px rgba(0, 212, 255, 0.1);
        }

        .project-card-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 1rem;
        }

        .project-title-section {
          display: flex;
          align-items: center;
          gap: 0.75rem;
        }

        .project-icon {
          font-size: 1.5rem;
        }

        .project-name {
          font-size: 1.1rem;
          font-weight: 600;
          color: rgba(255, 255, 255, 0.9);
          margin: 0;
        }

        .project-stats {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }

        .error-badge {
          padding: 0.3rem 0.6rem;
          border-radius: 0.5rem;
          font-size: 0.8rem;
          font-weight: 500;
        }

        .error-badge.high {
          background: rgba(239, 68, 68, 0.2);
          color: #ef4444;
          border: 1px solid rgba(239, 68, 68, 0.3);
        }

        .error-badge.medium {
          background: rgba(245, 158, 11, 0.2);
          color: #f59e0b;
          border: 1px solid rgba(245, 158, 11, 0.3);
        }

        .error-badge.low {
          background: rgba(16, 185, 129, 0.2);
          color: #10b981;
          border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .project-meta {
          font-size: 0.8rem;
          color: rgba(255, 255, 255, 0.4);
        }

        .last-error-time {
          display: flex;
          align-items: center;
          gap: 0.3rem;
        }

        .recent-errors {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }

        .recent-errors h4 {
          font-size: 0.85rem;
          font-weight: 500;
          color: rgba(255, 255, 255, 0.6);
          margin: 0 0 0.25rem 0;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .error-row {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.5rem;
          background: rgba(255, 255, 255, 0.03);
          border-radius: 6px;
          font-size: 0.85rem;
        }

        .error-row.high {
          border-left: 2px solid #ef4444;
        }

        .error-row.medium {
          border-left: 2px solid #f59e0b;
        }

        .error-row.low {
          border-left: 2px solid #10b981;
        }

        .error-severity-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          flex-shrink: 0;
        }

        .error-row.high .error-severity-dot {
          background: #ef4444;
        }

        .error-row.medium .error-severity-dot {
          background: #f59e0b;
        }

        .error-row.low .error-severity-dot {
          background: #10b981;
        }

        .error-text {
          color: rgba(255, 255, 255, 0.7);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .fix-all-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 0.5rem;
          padding: 0.75rem 1rem;
          background: linear-gradient(135deg, rgba(0, 212, 255, 0.2), rgba(139, 92, 246, 0.2));
          border: 1px solid rgba(0, 212, 255, 0.3);
          border-radius: 8px;
          color: rgba(255, 255, 255, 0.9);
          font-size: 0.9rem;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
          margin-top: auto;
        }

        .fix-all-btn:hover {
          background: linear-gradient(135deg, rgba(0, 212, 255, 0.3), rgba(139, 92, 246, 0.3));
          border-color: rgba(0, 212, 255, 0.5);
          transform: translateY(-1px);
        }

        .no-projects {
          grid-column: 1 / -1;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 1rem;
          padding: 3rem;
          color: rgba(255, 255, 255, 0.5);
        }

        .no-projects-icon {
          font-size: 3rem;
          color: #10b981;
        }

        .no-projects p {
          font-size: 1.1rem;
          margin: 0;
        }
      `}</style>
    </div>
  );
};
