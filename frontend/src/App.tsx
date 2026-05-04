import React, { useState, useEffect } from 'react';
import { LoadingScreen } from './components/LoadingScreen';
import { LockScreen } from './components/LockScreen';
import { OperatorHUD } from './components/dashboard/OperatorHUD';
import HandTracker from './components/HandTracker';
import { VoiceProvider, useVoice } from './contexts/VoiceContext';
import type { ErrorItem, Project } from './types';

// Removed mock data
const mockProjects: Project[] = [];

const mockErrors: ErrorItem[] = [];

// Inner App component that uses voice context
const AppContent: React.FC = () => {
  const { messages, wsConnected: _wsConnected } = useVoice();
  const [isLoading, setIsLoading] = useState(true);
  const [locked, setLocked] = useState(true);
  const [mobileMode, setMobileMode] = useState(false);
  useState('dashboard');
  const [activeModel, setActiveModel] = useState('qwen2.5-coder');
  const [_errors, setErrors] = useState<ErrorItem[]>(mockErrors);
  const [_projects, setProjects] = useState<Project[]>(mockProjects);
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
  const [_cpuHistory, setCpuHistory] = useState<number[]>(Array(60).fill(0));

  // Service health check
  const [_apiConnected, setApiConnected] = useState(false);
  const [_ollamaConnected, setOllamaConnected] = useState(false);

  // Initial loading simulation
  useEffect(() => {
    const timer = setTimeout(() => {
      setIsLoading(false);
    }, 2000);
    return () => clearTimeout(timer);
  }, []);

  // Check API and Ollama health
  useEffect(() => {
    const abortController = new AbortController();

    const checkServices = async () => {
      // Check API with retry
      let retries = 0;
      const maxRetries = 3;
      while (retries < maxRetries) {
        try {
          const res = await fetch('http://localhost:5050/errors', {
            signal: abortController.signal,
            cache: 'no-store'
          });
          setApiConnected(res.ok);
          if (res.ok) {
            const data = await res.json();
            setErrors(data);
          }
          break;
        } catch (e) {
          if ((e as Error).name === 'AbortError') return;
          retries++;
          if (retries >= maxRetries) {
            setApiConnected(false);
          } else {
            await new Promise(r => setTimeout(r, 1000 * retries));
          }
        }
      }
    };

    checkServices();
    const interval = setInterval(checkServices, 10000); // Reduced from 5s to 10s
    return () => {
      abortController.abort();
      clearInterval(interval);
    };
  }, []);

  // Check Ollama separately - only when API is connected, and much less frequently
  useEffect(() => {
    if (!_apiConnected) {
      setOllamaConnected(false);
      return;
    }

    const abortController = new AbortController();

    const checkOllama = async () => {
      try {
        const res = await fetch('http://localhost:11434/api/tags', {
          signal: abortController.signal,
          cache: 'no-store'
        });
        setOllamaConnected(res.ok);
      } catch (e) {
        if ((e as Error).name !== 'AbortError') {
          setOllamaConnected(false);
        }
      }
    };

    checkOllama();
    const interval = setInterval(checkOllama, 30000); // Only check every 30 seconds
    return () => {
      abortController.abort();
      clearInterval(interval);
    };
  }, [_apiConnected]);

  // Process WebSocket messages
  useEffect(() => {
    if (messages.length > 0) {
      const latestMessage = messages[messages.length - 1];
      console.log('[App] WebSocket message:', latestMessage);

      if ((latestMessage as any).model) {
        setActiveModel((latestMessage as any).model);
      }

      // Proactive alert from backend — update error list
      if ((latestMessage as any).type === 'proactive_alert') {
        const alertMsg = latestMessage as any;
        const newError = {
          id: Date.now(),
          project_name: alertMsg.project || 'System',
          error_text: alertMsg.error || alertMsg.text,
          severity: 'high' as const,
          timestamp: new Date().toISOString(),
          suggested_fix: '',
          fixed: false,
        };
        setErrors(prev => [newError, ...prev].slice(0, 20));
      }
    }
  }, [messages]);

  // Poll real project statuses from watcher DB every 10 seconds
  useEffect(() => {
    const abortController = new AbortController();
    
    const fetchProjects = async () => {
      let retries = 0;
      const maxRetries = 3;
      
      while (retries < maxRetries) {
        try {
          const res = await fetch('http://localhost:5050/projects', {
            signal: abortController.signal,
            cache: 'no-store'
          });
          if (res.ok) {
            const data = await res.json();
            if (data && data.length > 0) {
              setProjects(prev => {
                const updated = [...prev];
                data.forEach((dbProj: { name: string; status: string }) => {
                  const idx = updated.findIndex(p => p.name.toLowerCase() === dbProj.name.toLowerCase());
                  if (idx >= 0) {
                    updated[idx] = { ...updated[idx], status: dbProj.status as any };
                  } else {
                    updated.push({
                      id: dbProj.name,
                      name: dbProj.name,
                      status: dbProj.status as any,
                      path: `/projects/${dbProj.name.toLowerCase()}`,
                      type: 'other',
                    });
                  }
                });
                return updated;
              });
            }
            return; // Success, exit retry loop
          } else {
            throw new Error(`HTTP ${res.status}`);
          }
        } catch (e) {
          if ((e as Error).name === 'AbortError') return;
          retries++;
          if (retries < maxRetries) {
            await new Promise(r => setTimeout(r, 1000 * retries));
          }
        }
      }
    };
    fetchProjects();
    const interval = setInterval(fetchProjects, 10000);
    return () => {
      abortController.abort();
      clearInterval(interval);
    };
  }, []);

  // Fetch real system vitals every 5 seconds with error handling and retry
  useEffect(() => {
    let retryDelay = 5000;
    let intervalId: ReturnType<typeof setTimeout> | null = null;
    
    const fetchSystemVitals = async () => {
      try {
        const res = await fetch('http://localhost:5050/system', {
          signal: AbortSignal.timeout(10000) // 10 second timeout
        });
        
        if (res.ok) {
          const data = await res.json();
          retryDelay = 5000; // Reset retry delay on success
          
          setVitals({
            cpu: data.cpu_percent ?? 0,
            memory: data.ram_percent ?? 0,
            tempCPU: data.cpu_temp ?? null,
            tempGPU: data.gpu_temp ?? null,
            hasTemperatures: data.has_temperatures || false,
            ramUsedGB: data.ram_used_gb ?? 0,
            ramTotalGB: data.ram_total_gb ?? 0,
            // Drive C: Windows
            diskCPercent: data.disk_c_percent ?? 0,
            diskCLabel: data.disk_c_label || "Windows (C:)",
            diskCUsedGB: data.disk_c_used_gb ?? 0,
            diskCTotalGB: data.disk_c_total_gb ?? 0,
            // Drive D: Micro SSD
            diskDPercent: data.disk_d_percent ?? 0,
            diskDLabel: data.disk_d_label || "Micro SSD (D:)",
            diskDUsedGB: data.disk_d_used_gb ?? 0,
            diskDTotalGB: data.disk_d_total_gb ?? 0,
            // Drive E: HDD
            diskEPercent: data.disk_e_percent ?? 0,
            diskELabel: data.disk_e_label || "HDD (E:)",
            diskEUsedGB: data.disk_e_used_gb ?? 0,
            diskETotalGB: data.disk_e_total_gb ?? 0,
          });
          // Update CPU history for live graph
          setCpuHistory(prev => {
            const newHistory = [...prev.slice(1), data.cpu_percent ?? 0];
            return newHistory;
          });
        } else {
          throw new Error(`HTTP ${res.status}`);
        }
      } catch (err) {
        console.error('[System] Failed to fetch vitals:', err);
        // Show "Backend Offline" state
        setVitals(prev => ({
          ...prev,
          cpu: 0,
          memory: 0,
          tempCPU: null,
          tempGPU: null,
          hasTemperatures: false,
        }));
        // Exponential backoff for retries (max 30 seconds)
        retryDelay = Math.min(retryDelay * 1.5, 30000);
      }
    };

    // Initial fetch
    fetchSystemVitals();
    
    // Polling with dynamic interval based on retry delay
    const scheduleNext = () => {
      intervalId = setTimeout(() => {
        fetchSystemVitals().then(scheduleNext);
      }, retryDelay);
    };
    scheduleNext();
    
    return () => {
      if (intervalId) clearTimeout(intervalId);
    };
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

  // Check if on mobile device on load
  useEffect(() => {
    const checkMobile = () => {
      const isMobile = window.innerWidth < 768 || /Android|iPhone|iPad/i.test(navigator.userAgent);
      if (isMobile) {
        setMobileMode(true);
      }
    };
    checkMobile();
  }, []);

  return (
    <>
      {locked && <LockScreen onUnlock={() => setLocked(false)} />}
      <LoadingScreen isLoading={isLoading} />

      {/* Mobile Mode Toggle Button - Floating */}
      {!isLoading && !locked && (
        <button
          onClick={() => setMobileMode(!mobileMode)}
          style={{
            position: 'fixed',
            bottom: '20px',
            right: '20px',
            zIndex: 9999,
            width: '50px',
            height: '50px',
            borderRadius: '50%',
            background: mobileMode ? '#00ff96' : '#00b4ff',
            border: '2px solid rgba(255,255,255,0.3)',
            color: '#fff',
            fontSize: '24px',
            cursor: 'pointer',
            boxShadow: '0 4px 15px rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'all 0.3s ease'
          }}
          title={mobileMode ? 'Exit Mobile Mode' : 'Enter Mobile Mode'}
        >
          {mobileMode ? '📱' : '🖥️'}
        </button>
      )}

      {/* HUD only mounts after login — no network calls leak through the lock screen */}
      {!isLoading && !locked && (
        <OperatorHUD
          vitals={vitals}
          activeModel={activeModel}
          mobileMode={mobileMode}
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
