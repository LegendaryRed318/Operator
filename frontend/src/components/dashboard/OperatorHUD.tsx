import React, { useRef, useEffect, useState } from 'react';
import Orb from '../Orb';
import { useVoice } from '../../contexts/VoiceContext';

interface Vitals { cpu: number; memory: number; tempCPU?: number | null; tempGPU?: number | null; hasTemperatures?: boolean; }

interface OperatorHUDProps {
  vitals: Vitals;
  activeModel?: string;
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

export const OperatorHUD: React.FC<OperatorHUDProps> = ({ vitals, activeModel: _activeModel }) => {
  const { state: voiceState, lastResponse, interimText, manualWake, sendTextCommand } = useVoice();
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
  const sleeping = false; // TODO: wire to sleep manager

  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString('en-GB', { hour12: false }));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (voiceState === 'speaking' && lastResponse) {
      setAiText(lastResponse);
    }
  }, [voiceState, lastResponse]);

  const loadSkillsSummary = async () => {
    try {
      const [skillsRes, validateRes] = await Promise.all([
        fetch('http://localhost:5050/skills'),
        fetch('http://localhost:5050/skills/validate'),
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
      const res = await fetch('http://localhost:5050/brain/profile');
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
      const res = await fetch('http://localhost:5050/vault/health');
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

  useEffect(() => {
    loadVaultHealth();
    const t = setInterval(loadVaultHealth, 15000);
    return () => clearInterval(t);
  }, []);

  const runSkillsReload = async () => {
    setSkillsBusy(true);
    try {
      await fetch('http://localhost:5050/skills/reload', { method: 'POST' });
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
      const res = await fetch('http://localhost:5050/brain/profile', {
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
      const res = await fetch('http://localhost:5050/brain/profile/note', {
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
      const res = await fetch('http://localhost:5050/models');
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
        {/* Grid bg */}
        <div style={{
          position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0,
          backgroundImage: 'linear-gradient(rgba(0,180,255,0.025) 1px,transparent 1px),linear-gradient(90deg,rgba(0,180,255,0.025) 1px,transparent 1px)',
          backgroundSize: '40px 40px',
        }} />

        {/* TOPBAR */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '15px 30px',
          background: 'transparent', zIndex: 10, position: 'absolute', top: 0, width: '100%', boxSizing: 'border-box'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 12, height: 12, borderRadius: '50%', background: sleeping ? '#ffaa00' : '#00ff96', boxShadow: `0 0 10px ${sleeping ? '#ffaa00' : '#00ff96'}` }} />
            <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.2em', color: 'rgba(255,255,255,0.8)', fontFamily: "'Share Tech Mono', monospace" }}>{clock}</div>
          </div>
          <div style={{ fontSize: 16, letterSpacing: '0.4em', color: 'rgba(0,180,255,0.9)', fontFamily: "'Orbitron', sans-serif", fontWeight: 700 }}>
            JARVIS CORE
          </div>
          <div style={{ fontSize: 11, letterSpacing: '0.12em', color: 'rgba(255,255,255,0.5)', fontFamily: "'Share Tech Mono', monospace" }}>
            {formatModelName(modelsData.active)}
          </div>
        </div>

        {/* FLOATING GAUGES */}
        <div style={{
          position: 'absolute', left: 40, top: '20%', display: 'flex', flexDirection: 'column', gap: 20, zIndex: 5,
          background: 'rgba(3,5,8,0.4)', padding: 20, borderRadius: 16, border: '1px solid rgba(0,180,255,0.1)', backdropFilter: 'blur(8px)'
        }}>
          <div style={{ fontSize: 10, letterSpacing: '0.2em', color: '#00b4ff', fontFamily: "'Share Tech Mono', monospace" }}>SYSTEM DIAGNOSTICS</div>
          <div><div style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)' }}>CPU</div><div style={{ fontSize: 18, color: '#00ff96' }}>{Math.round(vitals.cpu)}%</div></div>
          <div><div style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)' }}>RAM</div><div style={{ fontSize: 18, color: '#00b4ff' }}>{Math.round(vitals.memory)}%</div></div>
          {vitals.hasTemperatures && vitals.tempCPU && <div><div style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)' }}>TEMP</div><div style={{ fontSize: 18, color: vitals.tempCPU > 80 ? '#ff4444' : '#ffaa00' }}>{Math.round(vitals.tempCPU)}°C</div></div>}
          
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
        </div>

        {/* SKILLS ADMIN PANEL */}
        <div style={{
          position: 'absolute', right: 40, top: '20%', zIndex: 6,
          background: 'rgba(3,5,8,0.4)', padding: 16, borderRadius: 16,
          border: '1px solid rgba(0,180,255,0.12)', backdropFilter: 'blur(8px)',
          width: 300
        }}>
          <div style={{ fontSize: 10, letterSpacing: '0.2em', color: '#00b4ff', fontFamily: "'Share Tech Mono', monospace", marginBottom: 10 }}>
            SKILLS ADMIN
          </div>
          <div style={{ fontSize: 12, color: 'rgba(220,235,245,0.8)', lineHeight: 1.5, marginBottom: 12 }}>
            {skillsSummary}
          </div>
          <div style={{ fontSize: 11, color: 'rgba(170,220,255,0.8)', lineHeight: 1.4, marginBottom: 10 }}>
            {vaultStatus}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={loadSkillsSummary}
              disabled={skillsBusy}
              style={{ background: 'rgba(0,180,255,0.15)', border: '1px solid rgba(0,180,255,0.3)', color: '#9bdfff', borderRadius: 8, padding: '6px 10px', cursor: 'pointer' }}
            >
              Validate
            </button>
            <button
              onClick={runSkillsReload}
              disabled={skillsBusy}
              style={{ background: 'rgba(0,255,150,0.14)', border: '1px solid rgba(0,255,150,0.35)', color: '#9effc8', borderRadius: 8, padding: '6px 10px', cursor: 'pointer' }}
            >
              Reload
            </button>
          </div>
        </div>

        {/* BRAIN EDITOR PANEL */}
        <div style={{
          position: 'absolute', right: 40, bottom: 130, zIndex: 6,
          background: 'rgba(3,5,8,0.45)', padding: 14, borderRadius: 16,
          border: '1px solid rgba(0,180,255,0.14)', backdropFilter: 'blur(8px)',
          width: 360, maxHeight: 430, overflow: 'auto'
        }}>
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

        {/* ORB CENTRE */}
        <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', zIndex: 2 }}>
          <div style={{ transform: 'scale(1.8)', transition: 'transform 0.5s ease' }}>
            <Orb />
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

        {/* FLOATING CHAT INPUT */}
        <div style={{ position: 'absolute', bottom: 40, left: '50%', transform: 'translateX(-50%)', zIndex: 10, width: '40%', minWidth: 400 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'rgba(0,0,0,0.6)', border: '1px solid rgba(0,180,255,0.3)', borderRadius: 24, padding: '12px 20px', backdropFilter: 'blur(10px)' }}>
            <input
              ref={inputRef} type="text" placeholder="Speak or type to JARVIS..."
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
              style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', color: '#fff', fontSize: 14, fontFamily: "'Share Tech Mono', monospace", opacity: isSending ? 0.5 : 1 }}
            />
            <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'rgba(0,180,255,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#00b4ff' }} onClick={manualWake}> microphone</div>
          </div>
        </div>
      </div>
    </>
  );
};

export default OperatorHUD;