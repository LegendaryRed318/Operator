import React, { useState, useEffect, useRef } from 'react';
import { LoadingScreen } from './components/LoadingScreen';
import { LockScreen } from './components/LockScreen';
import { OperatorHUD } from './components/dashboard/OperatorHUD';
import HandTracker from './components/HandTracker';
import { VoiceProvider, useVoice } from './contexts/VoiceContext';
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
  useVoice(); // ensures VoiceContext is consumed so the provider is active
  const [isLoading, setIsLoading] = useState(true);
  const [locked, setLocked] = useState(true);
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
  const { connected, connect, messages } = useWebSocket();
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
      {locked && <LockScreen onUnlock={() => setLocked(false)} />}
      <LoadingScreen isLoading={isLoading} />

      {/* HUD only mounts after login — no network calls leak through the lock screen */}
      {!isLoading && !locked && (
        <OperatorHUD
          vitals={vitals}
          projects={projects}
          recentErrors={errors}
          cpuHistory={cpuHistory}
          activeView={activeView}
          onViewChange={setActiveView}
          wsConnected={connected}
          apiConnected={apiConnected}
          ollamaConnected={ollamaConnected}
        />
      )}

      {/* HandTracker runs regardless so a wave can unlock from the lock screen */}
      <HandTracker onWave={() => {
        console.log('[App] Wave detected — entering hotword mode');
        window.dispatchEvent(new CustomEvent('jarvis:wake'));
      }} />
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
