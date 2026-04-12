import React, { useState, useEffect, useRef } from 'react';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { LoadingScreen } from './components/LoadingScreen';
import { DashboardView } from './components/dashboard/DashboardView';
import { ProjectsView } from './components/ProjectsView';
import { SystemView } from './components/SystemView';
import { HandTracker } from './components/HandTracker';
import { VoiceProvider } from './contexts/VoiceContext';
import { useWebSocket } from './hooks/useWebSocket';
import type { ErrorItem, Project } from './types';

// Mock data for initial state
const mockProjects: Project[] = [
  { id: '1', name: 'Brainify', status: 'healthy', path: '/projects/brainify' },
  { id: '2', name: 'Brainify-AI', status: 'error', lastError: 'Module not found: ./config', path: '/projects/brainify-ai' },
  { id: '3', name: 'Brainify-Motions', status: 'fixing', path: '/projects/brainify-motions' },
];

const mockErrors: ErrorItem[] = [
  { id: 1, project_name: 'Brainify-AI', error_text: 'Module not found: ./config', severity: 'high', timestamp: new Date().toISOString(), suggested_fix: 'Check import path', fixed: false },
  { id: 2, project_name: 'Brainify', error_text: 'Deprecation warning in build', severity: 'low', timestamp: new Date().toISOString(), suggested_fix: 'Update dependency', fixed: false },
];

// Inner App component that uses voice context
const AppContent: React.FC = () => {
  const [isLoading, setIsLoading] = useState(true);
  const [activeView, setActiveView] = useState('dashboard');
  const [errors, setErrors] = useState<ErrorItem[]>(mockErrors);
  const [projects] = useState<Project[]>(mockProjects);
  const [vitals, setVitals] = useState({
    cpu: 0,
    memory: 0,
    tempCPU: null as number | null,
    tempGPU: null as number | null,
    hasTemperatures: false,
    ramUsedGB: 0,
    ramTotalGB: 0,
    // Drive C: Windows
    diskCPercent: 0,
    diskCLabel: "Windows (C:)",
    diskCUsedGB: 0,
    diskCTotalGB: 0,
    // Drive D: Micro SSD
    diskDPercent: 0,
    diskDLabel: "Micro SSD (D:)",
    diskDUsedGB: 0,
    diskDTotalGB: 0,
    // Drive E: HDD
    diskEPercent: 0,
    diskELabel: "HDD (E:)",
    diskEUsedGB: 0,
    diskETotalGB: 0,
  });

  // CPU history for live graph (last 60 seconds)
  const [cpuHistory, setCpuHistory] = useState<number[]>(Array(60).fill(0));

  // WebSocket hook with max 3 retries and 10s initial delay
  const { connected, offline, connecting, connect, messages } = useWebSocket();
  const hasConnectedRef = useRef(false); // Prevent duplicate connections

  // Service health check
  const [apiConnected, setApiConnected] = useState(false);
  const [ollamaConnected, setOllamaConnected] = useState(false);

  // Initial loading simulation
  useEffect(() => {
    const timer = setTimeout(() => {
      setIsLoading(false);
    }, 2000);
    return () => clearTimeout(timer);
  }, []);

  // Connect WebSocket once when loading completes
  useEffect(() => {
    if (!isLoading && !hasConnectedRef.current) {
      hasConnectedRef.current = true;
      connect();
    }
  }, [isLoading, connect]);

  // Check API and Ollama health
  useEffect(() => {
    const checkServices = async () => {
      // Check API
      try {
        const res = await fetch('http://localhost:5050/errors');
        setApiConnected(res.ok);
        if (res.ok) {
          const data = await res.json();
          setErrors(data);
        }
      } catch {
        setApiConnected(false);
      }

      // Check Ollama
      try {
        const res = await fetch('http://localhost:11434/api/tags');
        setOllamaConnected(res.ok);
      } catch {
        setOllamaConnected(false);
      }
    };

    checkServices();
    const interval = setInterval(checkServices, 5000);
    return () => clearInterval(interval);
  }, []);

  // Process WebSocket messages
  useEffect(() => {
    if (messages.length > 0) {
      const latestMessage = messages[messages.length - 1];
      console.log('[App] WebSocket message:', latestMessage);
      // Handle different message types here
    }
  }, [messages]);

  // Fetch real system vitals every 5 seconds
  useEffect(() => {
    const fetchSystemVitals = async () => {
      try {
        const res = await fetch('http://localhost:5050/system');
        if (res.ok) {
          const data = await res.json();
          setVitals({
            cpu: data.cpu_percent || 0,
            memory: data.ram_percent || 0,
            tempCPU: data.cpu_temp,
            tempGPU: data.gpu_temp,
            hasTemperatures: data.has_temperatures || false,
            ramUsedGB: data.ram_used_gb || 0,
            ramTotalGB: data.ram_total_gb || 0,
            // Drive C: Windows
            diskCPercent: data.disk_c_percent || 0,
            diskCLabel: data.disk_c_label || "Windows (C:)",
            diskCUsedGB: data.disk_c_used_gb || 0,
            diskCTotalGB: data.disk_c_total_gb || 0,
            // Drive D: Micro SSD
            diskDPercent: data.disk_d_percent || 0,
            diskDLabel: data.disk_d_label || "Micro SSD (D:)",
            diskDUsedGB: data.disk_d_used_gb || 0,
            diskDTotalGB: data.disk_d_total_gb || 0,
            // Drive E: HDD
            diskEPercent: data.disk_e_percent || 0,
            diskELabel: data.disk_e_label || "HDD (E:)",
            diskEUsedGB: data.disk_e_used_gb || 0,
            diskETotalGB: data.disk_e_total_gb || 0,
          });
          // Update CPU history for live graph
          setCpuHistory(prev => {
            const newHistory = [...prev.slice(1), data.cpu_percent || 0];
            return newHistory;
          });
        }
      } catch (err) {
        console.error('[System] Failed to fetch vitals:', err);
      }
    };

    fetchSystemVitals();
    const interval = setInterval(fetchSystemVitals, 5000);
    return () => clearInterval(interval);
  }, []);

  // Keyboard shortcut for command palette
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === 'k') {
        e.preventDefault();
        console.log('[App] Command palette triggered');
        // TODO: Show command palette
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <>
      <LoadingScreen isLoading={isLoading} />
      
      {!isLoading && (
        <div className="app-container">
          {/* HUD Grid Background */}
          <div className="hud-grid" />
          
          {/* Sidebar */}
          <Sidebar 
            activeView={activeView} 
            onViewChange={setActiveView}
            errorCount={errors.length}
          />

          {/* Main Content Area */}
          <div className="main-content">
            {/* Top Bar with Status */}
            <TopBar
              wsConnected={connected}
              wsOffline={offline}
              wsConnecting={connecting}
              apiConnected={apiConnected}
              ollamaConnected={ollamaConnected}
              activeModel="qwen2.5-coder"
              clientCount={1}
            />

            {/* View Content */}
            <main className="view-container">
              {activeView === 'dashboard' && (
                <DashboardView
                  vitals={vitals}
                  projects={projects}
                  recentErrors={errors}
                />
              )}
              
              {activeView === 'projects' && (
                <ProjectsView errors={errors} />
              )}
              
              {activeView === 'errors' && (
                <div className="placeholder-view">
                  <h2>Error Intelligence</h2>
                  <p>Detailed error analysis and fixes coming soon...</p>
                </div>
              )}
              
              {activeView === 'system' && (
                <SystemView vitals={vitals} cpuHistory={cpuHistory} />
              )}
              
              {activeView === 'chat' && (
                <div className="placeholder-view">
                  <h2>AI Assistant</h2>
                  <p>Direct chat with JARVIS coming soon...</p>
                </div>
              )}
              
              {activeView === 'settings' && (
                <div className="placeholder-view">
                  <h2>Settings</h2>
                  <p>Configuration panel coming soon...</p>
                </div>
              )}
            </main>
          </div>

          <style>{`
            .app-container {
              display: flex;
              height: 100vh;
              width: 100vw;
              background: #050508;
              overflow: hidden;
            }

            .main-content {
              flex: 1;
              display: flex;
              flex-direction: column;
              overflow: hidden;
            }

            .view-container {
              flex: 1;
              overflow: hidden;
              position: relative;
            }

            .placeholder-view {
              height: 100%;
              display: flex;
              flex-direction: column;
              align-items: center;
              justify-content: center;
              gap: 1rem;
              color: rgba(255, 255, 255, 0.5);
            }

            .placeholder-view h2 {
              font-size: 1.5rem;
              color: rgba(255, 255, 255, 0.8);
            }
          `}</style>
        </div>
      )}
      <HandTracker enabled={!isLoading} />
    </>
  );
};

// Main App wrapped with VoiceProvider
const App: React.FC = () => {
  return (
    <VoiceProvider>
      <AppContent />
    </VoiceProvider>
  );
};

export default App;
