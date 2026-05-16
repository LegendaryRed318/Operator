import React, { useRef, useEffect, useState } from 'react';
import Orb from '../Orb';
import { useVoice } from '../../contexts/VoiceContext';
import { getApiBaseUrl } from '../../utils/urls';
import { pushNotification } from '../../utils/notifications';

interface Vitals { cpu: number; memory: number; tempCPU?: number | null; tempGPU?: number | null; hasTemperatures?: boolean; }

interface OperatorHUDProps {
  vitals: Vitals;
  activeModel?: string;
  mobileMode?: boolean;
}

const Waveform: React.FC<{ active: boolean }> = ({ active }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const phaseRef = useRef(0);
  const frameRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;

    const draw = () => {
      frameRef.current = requestAnimationFrame(draw);
      const W = canvas.offsetWidth * window.devicePixelRatio;
      const H = canvas.offsetHeight * window.devicePixelRatio;
      if (canvas.width !== W) { canvas.width = W; canvas.height = H; }
      ctx.clearRect(0, 0, W, H);
      const mid = H / 2;
      ctx.beginPath();
      ctx.strokeStyle = active ? 'rgba(0,180,255,0.9)' : 'rgba(0,180,255,0.25)';
      ctx.lineWidth = 1.5 * window.devicePixelRatio;
      for (let x = 0; x < W; x++) {
        const t = x / W;
        const amp = active
          ? (Math.sin(t * 22 + phaseRef.current) * 0.35 + Math.sin(t * 40 + phaseRef.current * 1.4) * 0.25 + Math.sin(t * 14 - phaseRef.current * 0.8) * 0.2 + (Math.random() - 0.5) * 0.1) * H * 0.38
          : Math.sin(t * 8 + phaseRef.current) * H * 0.04;
        x === 0 ? ctx.moveTo(x, mid + amp) : ctx.lineTo(x, mid + amp);
      }
      ctx.stroke();
      phaseRef.current += active ? 0.14 : 0.025;
    };
    draw();
    return () => cancelAnimationFrame(frameRef.current);
  }, [active]);

  return <canvas ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block' }} />;
};

export const OperatorHUD: React.FC<OperatorHUDProps> = ({ vitals, activeModel: _activeModel, mobileMode = false }) => {
  const { 
    state: voiceState, interimText, manualWake, sendTextCommand, 
    messages, isConversationMode, toggleConversationMode, 
    wsConnected, ttsSource, setTtsSource, vadSensitivity, setVadSensitivity 
  } = useVoice();
  const inputRef = useRef<HTMLInputElement>(null);
  const [aiText, setAiText] = useState('Operator Online');
  const [clock, setClock] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [skillsSummary, setSkillsSummary] = useState('Loading skills...');
  const [skillsBusy, setSkillsBusy] = useState(false);
  const [brainProfileText, setBrainProfileText] = useState('Loading profile...');
  const [brainNote, setBrainNote] = useState('');
  const [brainStatus, setBrainStatus] = useState('Brain editor ready');
  const [brainBusy, setBrainBusy] = useState(false);
  const [vaultStatus, setVaultStatus] = useState('Vault: checking...');
  const [serviceHealth, setServiceHealth] = useState<any>({});
  const [errors, setErrors] = useState<any[]>([]);
  const [remoteDevices, setRemoteDevices] = useState<any[]>([]);
  const [remoteCommandInput, setRemoteCommandInput] = useState<{ [key: str]: string }>({});
  const sleeping = false; // TODO: wire to sleep manager
  
  const [wakeSensitivity, setWakeSensitivity] = useState(
    () => localStorage.getItem('jarvis_wake_sensitivity') || 'Normal'
  );
  const [orbMode, setOrbMode] = useState<'quality' | 'battery'>(
    () => (localStorage.getItem('jarvis_orb_mode') === 'battery' ? 'battery' : 'quality')
  );
  const [faceStatus, setFaceStatus] = useState('Unknown Person');
  const [faceStatusNote, setFaceStatusNote] = useState('No face recognized yet');
  const [faceRegistering, setFaceRegistering] = useState(false);
  const [faceRegisterProgress, setFaceRegisterProgress] = useState(0);
  const lastFaceLabelRef = useRef('');

  useEffect(() => {
    localStorage.setItem('jarvis_wake_sensitivity', wakeSensitivity);
  }, [wakeSensitivity]);

  useEffect(() => {
    localStorage.setItem('jarvis_orb_mode', orbMode);
  }, [orbMode]);

  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString('en-GB', { hour12: false }));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg.type === 'stream_chunk') {
        setAiText((lastMsg.partial || '') + ' █');
      } else if (lastMsg.type === 'response') {
        setAiText(lastMsg.text || "I'm sorry sir, I didn't catch that.");
      }
    }
  }, [messages]);

  useEffect(() => {
    const handleFaceEvents = (e: any) => {
      const event = e.detail?.event;
      const data = e.detail?.data || {};
      if (event === 'face_recognition') {
        const status = data.recognized ? `Recognized: ${data.label}` : 'Unknown Person';
        setFaceStatus(status);
        setFaceStatusNote(data.recognized ? `Confidence ${Math.round((data.confidence || 0) * 100)}%` : 'No stored biometric match');
      }
      if (event === 'face_register_progress') {
        setFaceRegistering(true);
        setFaceRegisterProgress(data.captured || 0);
        setFaceStatusNote('Capturing face samples...');
      }
      if (event === 'face_registered') {
        setFaceRegistering(false);
        setFaceRegisterProgress(REGISTRATION_SAMPLES);
        setFaceStatus(`Recognized: ${data.label}`);
        setFaceStatusNote('Face registration complete.');
      }
      if (event === 'face_register_started') {
        setFaceRegistering(true);
        setFaceRegisterProgress(0);
        setFaceStatus('Registering face...');
        setFaceStatusNote('Please hold still, capture in progress');
      }
      if (event === 'face_lost') {
        setFaceStatus('Unknown Person');
        setFaceStatusNote('Camera lost face input');
      }
    };

    window.addEventListener('vision:event', handleFaceEvents as EventListener);
    return () => window.removeEventListener('vision:event', handleFaceEvents as EventListener);
  }, []);

  useEffect(() => {
    if (!faceStatus.startsWith('Recognized: ')) return;
    if (lastFaceLabelRef.current === faceStatus) return;
    lastFaceLabelRef.current = faceStatus;
    const notify = async () => {
      await pushNotification('JARVIS Biometrics', `Identity confirmed: ${faceStatus.replace('Recognized: ', '')}`);
    };
    notify();
  }, [faceStatus]);

  const requestFaceRegistration = () => {
    window.dispatchEvent(new CustomEvent('vision:register'));
  };

  const REGISTRATION_SAMPLES = 5;

  const faceStatusColor = faceStatus.startsWith('Recognized: ') ? '#00ff96' : '#ff7788';

  const loadSkillsSummary = async () => {
    try {
      const [skillsRes, validateRes] = await Promise.all([
        fetch(`${getApiBaseUrl()}/skills`),
        fetch(`${getApiBaseUrl()}/skills/validate`),
      ]);
      if (!skillsRes.ok || !validateRes.ok) {
        throw new Error('skills fetch failed');
      }
      const skillsData = await skillsRes.json();
      const validateData = await validateRes.json();
      const builtInCount = skillsData?.count_built_in ?? 0;
      const loadedCount = skillsData?.count_loaded ?? 0;
      const errors = validateData?.error_count ?? 0;
      const warnings = validateData?.warning_count ?? 0;
      setSkillsSummary(`Built-in ${builtInCount} | Imported ${loadedCount} | Validation E:${errors} W:${warnings}`);
    } catch {
      setSkillsSummary('Skills API unavailable');
    }
  };

  useEffect(() => {
    loadSkillsSummary();
    const t = setInterval(loadSkillsSummary, 20000);
    return () => clearInterval(t);
  }, []);

  const loadBrainProfile = async () => {
    setBrainStatus('Loading brain profile...');
    try {
      const res = await fetch(`${getApiBaseUrl()}/brain/profile`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const profile = data?.profile ?? {};
      setBrainProfileText(JSON.stringify(profile, null, 2));
      setBrainStatus('Brain profile loaded');
    } catch {
      setBrainStatus('Failed to load brain profile');
      setBrainProfileText('{}');
    }
  };

  useEffect(() => {
    loadBrainProfile();
  }, []);

  const loadVaultHealth = async () => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/vault/health`);
      if (!res.ok) throw new Error('health failed');
      const data = await res.json();
      const vault = data?.vault || {};
      const connected = vault?.connected ? 'connected' : 'disconnected';
      const writable = vault?.writable ? 'writable' : 'read-only';
      const path = vault?.path || 'unknown';
      setVaultStatus(`Vault ${connected} | ${writable} | ${path}`);
    } catch {
      setVaultStatus('Vault: API unavailable');
    }
  };

  const loadDetailedHealth = async () => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/health/detailed`);
      if (res.ok) {
        const data = await res.json();
        setServiceHealth(data);
      }
    } catch (err) {
      console.error('Failed to fetch detailed health:', err);
    }
  };

  const loadErrors = async () => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/errors`);
      if (res.ok) {
        const data = await res.json();
        setErrors(data);
      }
    } catch (err) {
      console.error('Failed to fetch errors:', err);
    }
  };

  const loadRemoteDevices = async () => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/remote/devices`);
      if (res.ok) {
        const data = await res.json();
        setRemoteDevices(data.devices || []);
      }
    } catch (err) {
      console.error('Failed to fetch remote devices:', err);
    }
  };

  useEffect(() => {
    loadRemoteDevices();
    const t = setInterval(loadRemoteDevices, 10000); // Polling every 10s
    return () => clearInterval(t);
  }, []);

  const runRemoteCommand = async (deviceName: string) => {
    const cmd = remoteCommandInput[deviceName];
    if (!cmd) return;
    try {
      const res = await fetch(`${getApiBaseUrl()}/remote/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_name: deviceName, command: cmd })
      });
      if (res.ok) {
        const data = await res.json();
        if (data.result?.success) {
          pushNotification(`Remote: ${deviceName}`, `Command successful`);
        } else {
          pushNotification(`Remote: ${deviceName}`, `Command failed: ${data.result?.error}`, 'error');
        }
      }
    } catch (err) {
      console.error('Failed to run command:', err);
    }
    setRemoteCommandInput(prev => ({ ...prev, [deviceName]: '' }));
  };

  const applyFix = async (errorId: number) => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/fix/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ error_id: errorId }),
      });
      if (res.ok) {
        alert('Fix application triggered. Check logs for details.');
        loadErrors();
      }
    } catch (err) {
      console.error('Failed to apply fix:', err);
    }
  };

  useEffect(() => {
    loadVaultHealth();
    loadDetailedHealth();
    loadErrors();
    const t = setInterval(() => {
      loadVaultHealth();
      loadDetailedHealth();
      loadErrors();
    }, 15000);
    return () => clearInterval(t);
  }, []);

  const runSkillsReload = async () => {
    setSkillsBusy(true);
    try {
      await fetch(`${getApiBaseUrl()}/skills/reload`, { method: 'POST' });
      await loadSkillsSummary();
    } finally {
      setSkillsBusy(false);
    }
  };

  const saveBrainProfileMerge = async () => {
    setBrainBusy(true);
    setBrainStatus('Saving brain profile (merge)...');
    try {
      const parsed = JSON.parse(brainProfileText || '{}');
      const res = await fetch(`${getApiBaseUrl()}/brain/profile`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: parsed }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setBrainProfileText(JSON.stringify(data?.profile ?? parsed, null, 2));
      setBrainStatus('Brain profile saved');
    } catch {
      setBrainStatus('Save failed (check JSON format)');
    } finally {
      setBrainBusy(false);
    }
  };

  const appendBrainNote = async () => {
    if (!brainNote.trim()) return;
    setBrainBusy(true);
    setBrainStatus('Appending profile note...');
    try {
      const res = await fetch(`${getApiBaseUrl()}/brain/profile/note`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: brainNote.trim() }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setBrainNote('');
      setBrainStatus('Profile note saved');
    } catch {
      setBrainStatus('Failed to append note');
    } finally {
      setBrainBusy(false);
    }
  };

  const [modelsData, setModelsData] = useState<{ models: string[], active: string }>({ models: [], active: 'loading...' });

  const fetchModels = async () => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/models`);
      if (res.ok) {
        const data = await res.json();
        setModelsData(data);
      }
    } catch (err) {
      console.error('Failed to fetch models:', err);
    }
  };

  useEffect(() => {
    fetchModels();
    const t = setInterval(fetchModels, 10000);
    return () => clearInterval(t);
  }, []);

  const formatModelName = (name: string) => {
    const n = name.toLowerCase();
    if (n.includes('deepseek-r1')) return 'DeepSeek R1';
    if (n.includes('qwen2.5-coder:7b')) return 'Qwen Coder 7B';
    if (n.includes('qwen2.5-coder:1.5b')) return 'Qwen Coder 1.5B';
    if (n.includes('llama3.2')) return 'Llama 3.2';
    if (n.includes('gemini')) return 'Gemini Flash';
    return name;
  };

  const getModelColor = (name: string) => {
    const n = name.toLowerCase();
    if (n.includes('7b')) return '#00ff96'; // Green
    if (n.includes('1.5b') || n.includes('3b')) return '#ffaa00'; // Yellow
    if (n.includes('gemini')) return '#00b4ff'; // Blue
    return '#a8cce0';
  };

  return (
    <>
      <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@400;700;900&family=Rajdhani:wght@400;600;700&display=swap" rel="stylesheet" />
      <div style={{
        height: '100vh', width: '100vw', background: '#030508', color: '#a8cce0',
        fontFamily: "'Rajdhani', sans-serif", overflow: 'hidden', position: 'fixed', inset: 0,
      }}>
        {/* Holographic Scanline */}
        <div className="scanline" />

        {/* HUD Grid overlay */}
        <div className="hud-grid" style={{ opacity: 0.2 }} />

        {/* Scanline Effect */}
        <div style={{
          position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 1,
          background: 'linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 212, 255, 0.02) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.01), rgba(0, 255, 0, 0.01), rgba(0, 0, 255, 0.01))',
          backgroundSize: '100% 4px, 3px 100%',
        }} />

        {/* TOPBAR */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '20px 40px',
          background: 'linear-gradient(to bottom, rgba(10,12,18,0.8), transparent)', 
          zIndex: 10, position: 'absolute', top: 0, width: '100%', boxSizing: 'border-box',
          borderBottom: '1px solid rgba(0,180,255,0.05)',
          backdropFilter: 'blur(10px)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 15 }}>
            <div style={{ 
              width: 12, height: 12, borderRadius: '2px', 
              background: sleeping ? 'var(--stark-amber)' : '#00ff96', 
              boxShadow: `0 0 12px ${sleeping ? 'var(--stark-amber)' : '#00ff96'}`,
              animation: 'pulse 2s infinite',
              transform: 'rotate(45deg)'
            }} />
            <div className="font-mono-tech" style={{ fontSize: 16, fontWeight: 700, letterSpacing: '0.2em', color: '#fff', textShadow: '0 0 10px rgba(255,255,255,0.3)' }}>{clock}</div>
          </div>
          <div className="font-header-tech" style={{ 
            fontSize: 22, color: '#00d4ff', 
            fontWeight: 900,
            textShadow: '0 0 15px rgba(0,212,255,0.5)',
            marginLeft: '40px'
          }}>
            OPERATOR <span style={{ opacity: 0.5, fontWeight: 400 }}>HUD</span>
          </div>
          <div className="font-mono-tech" style={{ 
            fontSize: 11, letterSpacing: '0.15em', color: 'rgba(0,180,255,0.6)', 
            background: 'rgba(0,212,255,0.05)',
            padding: '4px 12px',
            borderRadius: '2px',
            border: '1px solid rgba(0,212,255,0.1)'
          }}>
            SYSTEM: {formatModelName(modelsData.active).toUpperCase()}
          </div>
        </div>

        {/* FLOATING GAUGES - Hidden in mobile mode */}
        {!mobileMode && (
        <div 
          className="custom-scrollbar stark-panel"
          style={{
            position: 'absolute', left: 40, top: 100, bottom: 40,
            display: 'flex', flexDirection: 'column', gap: 24, zIndex: 5,
            padding: '24px', 
            backdropFilter: 'blur(15px)', width: 260,
            boxShadow: '0 10px 40px rgba(0,0,0,0.4)',
            overflowY: 'auto',
            overflowX: 'hidden'
          }}
        >
          <div className="font-mono-tech" style={{ fontSize: 10, letterSpacing: '0.3em', color: '#00b4ff', opacity: 0.8, marginBottom: -10 }}>BIOMETRIC STATUS</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)', letterSpacing: '0.1em' }}>CPU LOAD</div>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6 }}>
                <div style={{ fontSize: 24, color: vitals.cpu > 80 ? '#ff4444' : '#00ff96', fontWeight: 700, fontFamily: "'Share Tech Mono', monospace" }}>{Math.round(vitals.cpu)}</div>
                <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)', paddingBottom: 4 }}>%</div>
              </div>
              <div style={{ width: '100%', height: 2, background: 'rgba(255,255,255,0.05)', marginTop: 4 }}>
                <div style={{ width: `${vitals.cpu}%`, height: '100%', background: vitals.cpu > 80 ? '#ff4444' : '#00ff96', boxShadow: `0 0 10px ${vitals.cpu > 80 ? '#ff4444' : '#00ff96'}` }} />
              </div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)', letterSpacing: '0.1em' }}>MEMORY</div>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6 }}>
                <div style={{ fontSize: 24, color: '#00b4ff', fontWeight: 700, fontFamily: "'Share Tech Mono', monospace" }}>{Math.round(vitals.memory)}</div>
                <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)', paddingBottom: 4 }}>%</div>
              </div>
              <div style={{ width: '100%', height: 2, background: 'rgba(255,255,255,0.05)', marginTop: 4 }}>
                <div style={{ width: `${vitals.memory}%`, height: '100%', background: '#00b4ff', boxShadow: '0 0 10px #00b4ff' }} />
              </div>
            </div>
            {vitals.hasTemperatures && vitals.tempCPU && 
            <div>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)', letterSpacing: '0.1em' }}>CORE TEMP</div>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6 }}>
                <div style={{ fontSize: 24, color: vitals.tempCPU > 80 ? '#ff4444' : '#ffaa00', fontWeight: 700, fontFamily: "'Share Tech Mono', monospace" }}>{Math.round(vitals.tempCPU)}</div>
                <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.3)', paddingBottom: 4 }}>°C</div>
              </div>
            </div>
            }
          </div>
          
          {/* SERVICE STATUS LEDS */}
          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', marginBottom: 12, letterSpacing: '0.2em' }}>NETWORK NODES</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[
                { name: 'API GATEWAY', status: serviceHealth?.services?.api },
                { name: 'WS CLUSTER', status: serviceHealth?.services?.websocket },
                { name: 'NEURAL ENG', status: serviceHealth?.services?.ollama },
                { name: 'UPLINK', status: wsConnected }
              ].map((svc) => (
                <div key={svc.name} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.7)', textTransform: 'uppercase', letterSpacing: '0.15em' }}>{svc.name}</div>
                  <div style={{
                    width: 6, height: 6, borderRadius: '1px',
                    background: svc.status === true ? '#00ff96' : '#ff4444',
                    boxShadow: `0 0 8px ${svc.status === true ? '#00ff96' : '#ff4444'}`,
                    transform: 'rotate(45deg)'
                  }} />
                </div>
              ))}
            </div>
          </div>
          
          <div style={{ marginTop: 5 }}>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)', marginBottom: 4 }}>AI MODEL</div>
            <div style={{ fontSize: 16, color: getModelColor(modelsData.active), fontWeight: 600, letterSpacing: '0.05em' }}>
              {formatModelName(modelsData.active).toUpperCase()}
            </div>
            <div style={{ display: 'flex', gap: 4, marginTop: 6 }}>
              {modelsData.models.map((m, i) => (
                <div 
                  key={i} 
                  title={m}
                  style={{ 
                    width: 6, height: 6, borderRadius: '50%', 
                    background: m === modelsData.active ? getModelColor(m) : 'rgba(255,255,255,0.2)',
                    boxShadow: m === modelsData.active ? `0 0 5px ${getModelColor(m)}` : 'none'
                  }} 
                />
              ))}
            </div>
          </div>

          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)', marginBottom: 4 }}>WAKE SENSITIVITY</div>
            <div style={{ display: 'flex', gap: 4 }}>
              {['Strict', 'Normal', 'Loose'].map(level => (
                <div 
                  key={level} 
                  onClick={() => setWakeSensitivity(level)}
                  style={{ 
                    flex: 1, textAlign: 'center', fontSize: 10, padding: '4px 0', cursor: 'pointer',
                    background: wakeSensitivity === level ? 'rgba(0,180,255,0.3)' : 'rgba(255,255,255,0.05)',
                    border: `1px solid ${wakeSensitivity === level ? '#00b4ff' : 'transparent'}`,
                    borderRadius: 4, color: wakeSensitivity === level ? '#fff' : 'rgba(255,255,255,0.5)'
                  }}
                >
                  {level}
                </div>
              ))}
            </div>
          </div>

          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)', marginBottom: 4 }}>TTS SOURCE</div>
            <div style={{ display: 'flex', gap: 4 }}>
              {(['browser', 'server'] as const).map(source => (
                <div 
                  key={source} 
                  //@ts-ignore - setTtsSource exists in context now
                  onClick={() => setTtsSource(source)}
                  style={{ 
                    flex: 1, textAlign: 'center', fontSize: 10, padding: '4px 0', cursor: 'pointer',
                    //@ts-ignore
                    background: ttsSource === source ? 'rgba(0,255,150,0.25)' : 'rgba(255,255,255,0.05)',
                    //@ts-ignore
                    border: `1px solid ${ttsSource === source ? '#00ff96' : 'transparent'}`,
                    //@ts-ignore
                    borderRadius: 4, color: ttsSource === source ? '#fff' : 'rgba(255,255,255,0.5)',
                    textTransform: 'uppercase'
                  }}
                >
                  {source}
                </div>
              ))}
            </div>
          </div>

          <div style={{ marginTop: 10, padding: 14, borderRadius: 14, border: '1px solid rgba(0,180,255,0.2)', background: 'rgba(0,0,0,0.2)' }}>
            <div style={{ fontSize: 10, letterSpacing: '0.2em', color: '#00b4ff', marginBottom: 8, fontFamily: "'Share Tech Mono', monospace" }}>
              FACE RECOGNITION
            </div>
            <div style={{ fontSize: 12, marginBottom: 6, color: faceStatusColor, fontWeight: 600 }}>
              {faceStatus}
            </div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.65)', marginBottom: 10 }}>
              {faceStatusNote}
            </div>
            <button
              onClick={requestFaceRegistration}
              disabled={faceRegistering}
              style={{
                width: '100%', padding: '8px 10px', borderRadius: 10,
                border: `1px solid ${faceRegistering ? '#00b4ff' : 'rgba(0,255,150,0.4)'}`,
                background: faceRegistering ? 'rgba(0,180,255,0.16)' : 'rgba(0,255,150,0.12)',
                color: '#e9f9ff', cursor: faceRegistering ? 'not-allowed' : 'pointer',
                fontSize: 11, letterSpacing: '0.08em'
              }}
            >
              {faceRegistering ? `Capturing ${faceRegisterProgress}/5` : 'Register My Face'}
            </button>
          </div>

          <div style={{ marginTop: 10, padding: 14, borderRadius: 14, border: '1px solid rgba(0,180,255,0.15)', background: 'rgba(0,0,0,0.18)' }}>
            <div style={{ fontSize: 10, letterSpacing: '0.2em', color: '#00b4ff', marginBottom: 8, fontFamily: "'Share Tech Mono', monospace" }}>
              ORB PERFORMANCE
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              {(['quality', 'battery'] as const).map(mode => (
                <div
                  key={mode}
                  onClick={() => setOrbMode(mode)}
                  style={{
                    flex: 1,
                    textAlign: 'center',
                    padding: '6px 0',
                    borderRadius: 10,
                    cursor: 'pointer',
                    border: `1px solid ${orbMode === mode ? '#00b4ff' : 'rgba(255,255,255,0.1)'}`,
                    background: orbMode === mode ? 'rgba(0,180,255,0.18)' : 'rgba(255,255,255,0.05)',
                    color: orbMode === mode ? '#fff' : 'rgba(255,255,255,0.6)',
                    textTransform: 'uppercase',
                    fontSize: 10,
                    fontWeight: 700
                  }}
                >
                  {mode === 'quality' ? 'High Quality' : 'Battery Saver'}
                </div>
              ))}
            </div>
          </div>

          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)', marginBottom: 4 }}>VAD SENSITIVITY</div>
            <input
              type="range"
              min={0}
              max={100}
              value={vadSensitivity}
              onChange={(e) => setVadSensitivity(Number(e.target.value))}
              style={{ width: '100%' }}
            />
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.6)', marginTop: 4 }}>
              {vadSensitivity}%
            </div>
          </div>

          {/* ERROR MONITORING - Moved inside sidebar */}
          <div style={{ 
            marginTop: 20, padding: 16, borderRadius: 4, 
            background: 'rgba(20,5,5,0.3)', 
            border: '1px solid rgba(255,80,80,0.15)'
          }}>
            <div style={{ fontSize: 10, letterSpacing: '0.2em', color: '#ff5050', fontFamily: "'Share Tech Mono', monospace", marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
               <div style={{ width: 6, height: 6, borderRadius: '50%', background: errors.length > 0 ? '#ff5050' : '#00ff96', animation: errors.length > 0 ? 'pulse 1s infinite' : 'none' }} />
               ERROR MONITOR
            </div>
            {errors.length === 0 ? (
              <div style={{ fontSize: 11, color: 'rgba(0,255,150,0.4)', textAlign: 'center' }}>SYSTEM NOMINAL</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {errors.slice(0, 5).map((err) => (
                  <div key={err.id} style={{ 
                      padding: 10, background: 'rgba(255,50,50,0.05)', borderLeft: '2px solid #ff3232', 
                      borderRadius: 2, marginBottom: 8 
                    }}>
                      <div style={{ fontSize: 10, color: '#ff7a7a', fontWeight: 'bold' }}>{err.severity.toUpperCase()}</div>
                      <div style={{ fontSize: 11, color: '#fff', margin: '4px 0' }}>{err.error_text}</div>
                      <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.4)' }}>{new Date(err.timestamp).toLocaleString()}</div>
                      <button 
                        onClick={() => applyFix(err.id)}
                        style={{
                          marginTop: 8, padding: '4px 8px', background: 'rgba(255,50,50,0.15)',
                          border: '1px solid rgba(255,50,50,0.3)', color: '#ff7a7a',
                          fontSize: 9, cursor: 'pointer', borderRadius: 2
                        }}
                      >
                        APPLY FIX
                      </button>
                    </div>
                ))}
              </div>
            )}
          </div>
        </div>
        )}

        {!mobileMode && (
        <div 
          className="stark-panel"
          style={{
            position: 'absolute', left: 320, top: '15%', zIndex: 6,
            padding: '20px',
            backdropFilter: 'blur(20px)',
            width: 320, maxHeight: '60%', overflow: 'hidden',
            boxShadow: '0 15px 50px rgba(0,0,0,0.5)',
            display: 'flex', flexDirection: 'column'
          }}
        >
          <div style={{ fontSize: 10, letterSpacing: '0.3em', color: '#00d4ff', fontFamily: "'Share Tech Mono', monospace", marginBottom: 15, opacity: 0.8 }}>TRANSMISSION HISTORY</div>
          <div style={{ 
            overflowY: 'auto', flex: 1, paddingRight: 10,
            display: 'flex', flexDirection: 'column', gap: 12
          }}>
            {messages.filter(m => m.type === 'response' || m.type === 'voice_command' || m.type === 'command').slice(-10).map((msg, i) => (
              <div key={i} style={{ 
                fontSize: 12, 
                borderLeft: `2px solid ${msg.type === 'response' ? '#00d4ff' : 'rgba(255,255,255,0.1)'}`,
                paddingLeft: 10,
                paddingBottom: 4
              }}>
                <div style={{ fontSize: 9, opacity: 0.4, textTransform: 'uppercase', marginBottom: 2 }}>
                  {msg.type === 'response' ? 'JARVIS' : 'USER'}
                </div>
                <div style={{ color: msg.type === 'response' ? '#e9f9ff' : '#00ff96', lineHeight: 1.4, fontFamily: "'Share Tech Mono', monospace" }}>
                  {msg.text || msg.partial || ''}
                </div>
              </div>
            ))}
          </div>
        </div>
        )}

        {!mobileMode && (
        <div 
          className="custom-scrollbar stark-panel"
          style={{
            position: 'absolute', right: 40, top: 100, bottom: 40,
            zIndex: 6,
            padding: '20px',
            backdropFilter: 'blur(20px)',
            width: 320,
            boxShadow: '0 15px 50px rgba(0,0,0,0.5)',
            overflowY: 'auto',
            overflowX: 'hidden',
            display: 'flex',
            flexDirection: 'column',
            gap: 24
          }}
        >
          <div>
            <div style={{ fontSize: 10, letterSpacing: '0.3em', color: '#00d4ff', fontFamily: "'Share Tech Mono', monospace", marginBottom: 15, opacity: 0.8 }}>SYSTEM CAPABILITIES</div>
            <div style={{ fontSize: 11, color: 'rgba(220,235,245,0.7)', lineHeight: 1.6, marginBottom: 10, fontFamily: "'Share Tech Mono', monospace" }}>
              {skillsSummary}
            </div>
            <div style={{ fontSize: 9, color: 'rgba(0,212,255,0.6)', letterSpacing: '0.1em', marginBottom: 15, fontFamily: "'Share Tech Mono', monospace" }}>
              {vaultStatus.toUpperCase()}
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button
                onClick={loadSkillsSummary}
                disabled={skillsBusy}
                style={{
                  flex: 1, padding: '8px', background: 'rgba(255,255,255,0.05)',
                  border: '1px solid rgba(255,255,255,0.1)', color: 'rgba(255,255,255,0.6)',
                  fontFamily: "'Share Tech Mono', monospace", fontSize: 10,
                  cursor: 'pointer', borderRadius: '2px'
                }}
              >
                VALIDATE
              </button>
              <button
                onClick={runSkillsReload}
                disabled={skillsBusy}
                style={{
                  flex: 1, padding: '8px', background: 'rgba(0,212,255,0.08)',
                  border: '1px solid rgba(0,212,255,0.2)', color: '#00d4ff',
                  fontFamily: "'Share Tech Mono', monospace", fontSize: 10,
                  cursor: 'pointer', borderRadius: '2px'
                }}
              >
                {skillsBusy ? 'BUSY...' : 'RELOAD'}
              </button>
            </div>
          </div>

          <div style={{ borderTop: '1px solid rgba(0,212,255,0.1)', paddingTop: 20 }}>
            <div style={{ fontSize: 10, letterSpacing: '0.2em', color: '#00b4ff', fontFamily: "'Share Tech Mono', monospace", marginBottom: 8 }}>
              JARVIS BRAIN EDITOR
            </div>
            <div style={{ fontSize: 11, color: 'rgba(220,235,245,0.8)', marginBottom: 8 }}>{brainStatus}</div>

            <textarea
              value={brainProfileText}
              onChange={(e) => setBrainProfileText(e.target.value)}
              style={{
                width: '100%',
                minHeight: 170,
                background: 'rgba(1,12,18,0.7)',
                color: '#c7f0ff',
                border: '1px solid rgba(0,180,255,0.25)',
                borderRadius: 8,
                fontFamily: "'Share Tech Mono', monospace",
                fontSize: 11,
                padding: 8,
                boxSizing: 'border-box'
              }}
            />
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <button
                onClick={loadBrainProfile}
                disabled={brainBusy}
                style={{ background: 'rgba(0,180,255,0.15)', border: '1px solid rgba(0,180,255,0.3)', color: '#9bdfff', borderRadius: 8, padding: '6px 10px', cursor: 'pointer' }}
              >
                Reload
              </button>
              <button
                onClick={saveBrainProfileMerge}
                disabled={brainBusy}
                style={{ background: 'rgba(0,255,150,0.14)', border: '1px solid rgba(0,255,150,0.35)', color: '#9effc8', borderRadius: 8, padding: '6px 10px', cursor: 'pointer' }}
              >
                Save Merge
              </button>
            </div>

            <textarea
              value={brainNote}
              onChange={(e) => setBrainNote(e.target.value)}
              placeholder="Add quick note to brain journal..."
              style={{
                width: '100%',
                minHeight: 70,
                marginTop: 10,
                background: 'rgba(1,12,18,0.7)',
                color: '#c7f0ff',
                border: '1px solid rgba(0,180,255,0.25)',
                borderRadius: 8,
                fontFamily: "'Share Tech Mono', monospace",
                fontSize: 11,
                padding: 8,
                boxSizing: 'border-box'
              }}
            />
            <div style={{ marginTop: 8 }}>
              <button
                onClick={appendBrainNote}
                disabled={brainBusy || !brainNote.trim()}
                style={{ background: 'rgba(255,170,0,0.14)', border: '1px solid rgba(255,170,0,0.35)', color: '#ffd893', borderRadius: 8, padding: '6px 10px', cursor: 'pointer' }}
              >
                Add Note
              </button>
            </div>
          </div>

          <div style={{ borderTop: '1px solid rgba(0,212,255,0.1)', paddingTop: 20 }}>
            <div style={{ fontSize: 10, letterSpacing: '0.2em', color: '#00b4ff', fontFamily: "'Share Tech Mono', monospace", marginBottom: 8 }}>
              REMOTE ADMIN BRIDGE
            </div>
            {remoteDevices.length === 0 ? (
              <div style={{ fontSize: 11, color: 'rgba(220,235,245,0.4)', fontStyle: 'italic' }}>No devices configured.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {remoteDevices.map(device => (
                  <div key={device.name} style={{ background: 'rgba(0,180,255,0.05)', border: '1px solid rgba(0,180,255,0.15)', padding: 10, borderRadius: 6 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                      <div style={{ fontSize: 12, color: '#e9f9ff', fontWeight: 'bold' }}>{device.name}</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div style={{ width: 6, height: 6, borderRadius: '50%', background: device.online ? '#00ff96' : '#ff4444', boxShadow: `0 0 5px ${device.online ? '#00ff96' : '#ff4444'}` }} />
                        <div style={{ fontSize: 9, color: device.online ? '#00ff96' : '#ff4444' }}>{device.online ? 'ONLINE' : 'OFFLINE'}</div>
                      </div>
                    </div>
                    <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)', marginBottom: 8 }}>{device.device_type.toUpperCase()} | {device.host}</div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <input 
                        type="text" 
                        value={remoteCommandInput[device.name] || ''}
                        onChange={e => setRemoteCommandInput(prev => ({ ...prev, [device.name]: e.target.value }))}
                        placeholder="Run command..."
                        style={{ flex: 1, background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', fontSize: 10, padding: '4px 6px', borderRadius: 4 }}
                      />
                      <button 
                        onClick={() => runRemoteCommand(device.name)}
                        style={{ background: 'rgba(0,180,255,0.2)', border: 'none', color: '#00d4ff', fontSize: 10, padding: '4px 8px', borderRadius: 4, cursor: 'pointer' }}
                      >
                        RUN
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
        )}

        {/* ORB CENTRE - Enlarged in mobile mode */}
        <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', zIndex: 2 }}>
          <div style={{ position: 'relative', transform: mobileMode ? 'scale(2.8)' : 'scale(1.8)', transition: 'transform 0.5s ease' }}>
            {/* Tech Rings */}
            <svg 
              className="animate-spin"
              style={{ 
                position: 'absolute', inset: -50, width: 400, height: 400, 
                opacity: 0.15, pointerEvents: 'none', 
                animationDuration: '20s', 
                color: 'var(--jarvis-accent)' 
              }} 
              viewBox="0 0 100 100"
            >
              <circle cx="50" cy="50" r="48" fill="none" stroke="currentColor" strokeWidth="0.5" strokeDasharray="10, 5" />
              <circle cx="50" cy="50" r="42" fill="none" stroke="currentColor" strokeWidth="0.2" />
            </svg>
            <svg 
              className="animate-spin"
              style={{ 
                position: 'absolute', inset: -30, width: 360, height: 360, 
                opacity: 0.1, pointerEvents: 'none', 
                animationDirection: 'reverse', 
                animationDuration: '12s', 
                color: 'var(--jarvis-accent)' 
              }} 
              viewBox="0 0 100 100"
            >
              <path d="M50 2 A48 48 0 0 1 98 50" fill="none" stroke="currentColor" strokeWidth="1" />
              <path d="M50 98 A48 48 0 0 1 2 50" fill="none" stroke="currentColor" strokeWidth="1" />
            </svg>
            <Orb performanceMode={orbMode} />
          </div>
          {/* Interim speech recognition feedback */}
          {interimText && (
            <div style={{ marginTop: 100, fontSize: 14, color: 'rgba(0,180,255,0.7)', fontStyle: 'italic', maxWidth: 600, textAlign: 'center' }}>
              Hearing: "{interimText}..."
            </div>
          )}
          <div style={{ marginTop: interimText ? 10 : 120, fontSize: 16, color: 'rgba(200,220,240,0.9)', maxWidth: 600, textAlign: 'center', lineHeight: 1.5 }}>
            {aiText}
          </div>
          {(voiceState === 'speaking' || voiceState === 'listening') && (
            <div style={{ width: 300, height: 50, marginTop: 20 }}><Waveform active={voiceState === 'speaking' || voiceState === 'listening'} /></div>
          )}
        </div>

        {/* FLOATING CHAT INPUT - Full width in mobile mode */}
        <div style={{ 
          position: 'absolute', bottom: 60, left: '50%', transform: 'translateX(-50%)', 
          zIndex: 10, width: mobileMode ? '92%' : '45%', 
          minWidth: mobileMode ? 'unset' : 480, 
          maxWidth: mobileMode ? '500px' : '700px' 
        }}>
          <div 
            className="stark-panel"
            style={{ 
              display: 'flex', alignItems: 'center', gap: 15, 
              padding: '16px 24px', 
              backdropFilter: 'blur(20px)',
              boxShadow: '0 20px 40px rgba(0,0,0,0.6)'
            }}
          >
            <div 
              onClick={toggleConversationMode}
              style={{ 
                padding: '4px 10px', borderRadius: '2px', cursor: 'pointer', fontSize: 9, fontWeight: '900', letterSpacing: '2px',
                background: isConversationMode ? 'rgba(0,255,150,0.1)' : 'rgba(255,255,255,0.05)', 
                border: `1px solid ${isConversationMode ? '#00ff96' : 'rgba(255,255,255,0.2)'}`, 
                color: isConversationMode ? '#00ff96' : 'rgba(255,255,255,0.5)',
                textTransform: 'uppercase',
                transition: 'all 0.3s ease'
              }}
            >
              Mode: {isConversationMode ? 'Active' : 'Standby'}
            </div>
            <input
              ref={inputRef} type="text" placeholder="AWAITING INPUT..."
              autoComplete="off"
              disabled={isSending}
              onKeyDown={async (e) => {
                if (e.key === 'Enter' && inputRef.current && inputRef.current.value.trim()) {
                  const text = inputRef.current.value.trim();
                  inputRef.current.value = '';
                  setIsSending(true);
                  try {
                    await sendTextCommand(text);
                  } finally {
                    setIsSending(false);
                  }
                }
              }}
              style={{ 
                flex: 1, background: 'transparent', border: 'none', outline: 'none', 
                color: '#fff', fontSize: 15, 
                fontFamily: "'Share Tech Mono', monospace", 
                letterSpacing: '0.05em',
                opacity: isSending ? 0.3 : 1 
              }}
            />
            <div 
              style={{ 
                width: 36, height: 36, borderRadius: '50%', 
                background: voiceState === 'listening' ? 'rgba(0,255,150,0.2)' : 'rgba(0,180,255,0.1)', 
                display: 'flex', alignItems: 'center', justifyContent: 'center', 
                cursor: 'pointer', color: voiceState === 'listening' ? '#00ff96' : '#00b4ff',
                boxShadow: voiceState === 'listening' ? '0 0 15px #00ff96' : 'none',
                transition: 'all 0.3s ease',
                border: `1px solid ${voiceState === 'listening' ? '#00ff96' : 'rgba(0,212,255,0.2)'}`
              }} 
              onClick={manualWake}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                <line x1="12" y1="19" x2="12" y2="23"></line>
                <line x1="8" y1="23" x2="16" y2="23"></line>
              </svg>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

export default OperatorHUD;