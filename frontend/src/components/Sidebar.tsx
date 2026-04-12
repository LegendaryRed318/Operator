import React from 'react';

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  badge?: number;
}

interface SidebarProps {
  activeView: string;
  onViewChange: (view: string) => void;
  errorCount: number;
}

export const Sidebar: React.FC<SidebarProps> = ({ activeView, onViewChange, errorCount }) => {
  const navItems: NavItem[] = [
    { id: 'dashboard', label: 'Dashboard', icon: <span style={{ fontSize: '1.1rem' }}>◈</span> },
    { id: 'projects', label: 'Projects', icon: <span style={{ fontSize: '1.1rem' }}>📁</span> },
    { id: 'errors', label: 'Errors', icon: <span style={{ fontSize: '1.1rem' }}>⚠️</span>, badge: errorCount > 0 ? errorCount : undefined },
    { id: 'system', label: 'System', icon: <span style={{ fontSize: '1.1rem' }}>◉</span> },
    { id: 'chat', label: 'AI Chat', icon: <span style={{ fontSize: '1.1rem' }}>💬</span> },
    { id: 'settings', label: 'Settings', icon: <span style={{ fontSize: '1.1rem' }}>⚙️</span> },
  ];

  return (
    <aside className="sidebar">
      {/* Logo Section */}
      <div className="sidebar-header">
        <div className="logo-orb">
          <div className="logo-core"></div>
          <div className="logo-ring"></div>
        </div>
        <div className="logo-text">
          <span className="logo-title">JARVIS</span>
          <span className="logo-subtitle">System Guardian</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <button
            key={item.id}
            className={`nav-item ${activeView === item.id ? 'active' : ''}`}
            onClick={() => onViewChange(item.id)}
          >
            <span className="nav-icon">{item.icon}</span>
            <span className="nav-label">{item.label}</span>
            {item.badge && (
              <span className="nav-badge">{item.badge}</span>
            )}
          </button>
        ))}
      </nav>

      {/* Gaming Mode Toggle */}
      <div className="sidebar-footer">
        <button className="gaming-toggle">
          <span style={{ fontSize: '1rem' }}>⚡</span>
          <span>Gaming Mode</span>
        </button>
      </div>

      <style>{`
        .sidebar {
          width: 240px;
          height: 100%;
          background: rgba(5, 5, 8, 0.95);
          border-right: 1px solid rgba(0, 212, 255, 0.1);
          display: flex;
          flex-direction: column;
          padding: 1.5rem 1rem;
        }

        .sidebar-header {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding-bottom: 2rem;
          border-bottom: 1px solid rgba(0, 212, 255, 0.1);
          margin-bottom: 1.5rem;
        }

        .logo-orb {
          position: relative;
          width: 40px;
          height: 40px;
        }

        .logo-core {
          position: absolute;
          inset: 8px;
          background: radial-gradient(circle at 30% 30%, #00d4ff, #0088aa);
          border-radius: 50%;
          box-shadow: 0 0 10px rgba(0, 212, 255, 0.5);
        }

        .logo-ring {
          position: absolute;
          inset: 0;
          border: 2px solid rgba(0, 212, 255, 0.3);
          border-radius: 50%;
          animation: spin 3s linear infinite;
        }

        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }

        .logo-text {
          display: flex;
          flex-direction: column;
        }

        .logo-title {
          font-family: 'JetBrains Mono', monospace;
          font-size: 1.25rem;
          font-weight: 700;
          color: #00d4ff;
          letter-spacing: 0.1em;
          text-shadow: 0 0 10px rgba(0, 212, 255, 0.5);
        }

        .logo-subtitle {
          font-size: 0.7rem;
          color: rgba(255, 255, 255, 0.4);
          letter-spacing: 0.05em;
          text-transform: uppercase;
        }

        .sidebar-nav {
          flex: 1;
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }

        .nav-item {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 0.75rem 1rem;
          border-radius: 8px;
          border: none;
          background: transparent;
          color: rgba(255, 255, 255, 0.6);
          font-family: 'Inter', sans-serif;
          font-size: 0.9rem;
          cursor: pointer;
          transition: all 0.2s ease;
          text-align: left;
        }

        .nav-item:hover {
          background: rgba(0, 212, 255, 0.05);
          color: rgba(255, 255, 255, 0.9);
        }

        .nav-item.active {
          background: linear-gradient(135deg, rgba(0, 212, 255, 0.15), rgba(0, 212, 255, 0.05));
          color: #00d4ff;
          box-shadow: 0 0 15px rgba(0, 212, 255, 0.1);
        }

        .nav-icon {
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .nav-badge {
          margin-left: auto;
          background: #ef4444;
          color: white;
          font-size: 0.7rem;
          font-weight: 600;
          padding: 0.15rem 0.5rem;
          border-radius: 10px;
          min-width: 20px;
          text-align: center;
        }

        .sidebar-footer {
          padding-top: 1.5rem;
          border-top: 1px solid rgba(0, 212, 255, 0.1);
        }

        .gaming-toggle {
          width: 100%;
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 0.75rem 1rem;
          border-radius: 8px;
          border: 1px solid rgba(139, 92, 246, 0.3);
          background: linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(139, 92, 246, 0.05));
          color: #8b5cf6;
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.85rem;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .gaming-toggle:hover {
          background: linear-gradient(135deg, rgba(139, 92, 246, 0.25), rgba(139, 92, 246, 0.1));
          box-shadow: 0 0 15px rgba(139, 92, 246, 0.3);
          transform: translateY(-1px);
        }
      `}</style>
    </aside>
  );
};
