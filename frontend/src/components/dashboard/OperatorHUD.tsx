import React, { useRef, useEffect, useState } from 'react';
import Orb from '../Orb';
import { useVoice } from '../../contexts/VoiceContext';

interface Project {
  id: string;
  name: string;
  status: 'healthy' | 'error' | 'fixing' | 'offline';
  lastError?: string;
  path: string;
}

interface ErrorItem {
  id: number;
  project_name: string;
  error_text: string;
  severity: 'low' | 'medium' | 'high';
  timestamp: string;
  fixed: boolean;
}

interface Vitals {
  cpu: number;
  memory: number;
  tempCPU?: number | null;
  tempGPU?: number | null;
  hasTemperatures?: boolean;
  ramUsedGB?: number;
  ramTotalGB?: number;
  diskCPercent?: number;
  diskCLabel?: string;
  diskCUsedGB?: number;
  diskCTotalGB?: number;
  diskDPercent?: number;
  diskDLabel?: string;
  diskDUsedGB?: number;
  diskDTotalGB?: number;
  diskEPercent?: number;
  diskELabel?: string;
  diskEUsedGB?: number;
  diskETotalGB?: number;
}

interface OperatorHUDProps {
  vitals: Vitals;
  projects: Project[];
  recentErrors: ErrorItem[];
  cpuHistory: number[];
  activeView: string;
  onViewChange: (view: string) => void;
  wsConnected: boolean;
  apiConnected: boolean;
  ollamaConnected: boolean;
}

// Arc gauge component
const ArcGauge: React.FC<{
  value: number;
  max?: number;
  label: string;
  detail: string;
  color: string;
  unit?: string;
  warn?: boolean;
}> = ({ value, label, detail, color, unit = '%', warn }) => {
  const pct = Math.min(value / 100, 1);
  const circumference = 2 * Math.PI * 26;
  const offset = circumference * (1 - pct);
  const displayColor = warn ? '#ff4444' : color;

  return (
    <div style={{
      background: 'rgba(0,180,255,0.03)',
      border: `1px solid rgba(0,180,255,0.12)`,
      borderRadius: 12,
      padding: '12px',
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      cursor: 'pointer',
      transition: 'border-color 0.2s',
    }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = 'rgba(0,180,255,0.3)')}
      onMouseLeave={e => (e.currentTarget.style.borderColor = 'rgba(0,180,255,0.12)')}
    >
      <div style={{ position: 'relative', width: 64, height: 64, flexShrink: 0 }}>
        <svg width="64" height="64" viewBox="0 0 64 64">
          <circle cx="32" cy="32" r="26" fill="none"
            stroke={`${displayColor}18`} strokeWidth="5" />
          <circle cx="32" cy="32" r="26" fill="none"
            stroke={displayColor} strokeWidth="5" strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            transform="rotate(-90 32 32)"
            style={{ transition: 'stroke-dashoffset 1s ease' }}
          />
        </svg>
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexDirection: 'column',
        }}>
          <span style={{
            fontSize: value > 99 ? 11 : 14,
            fontWeight: 700,
            color: displayColor,
            fontFamily: "'Orbitron', sans-serif",
            lineHeight: 1,
          }}>{Math.round(value)}{unit}</span>
        </div>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.08em', color: 'rgba(255,255,255,0.85)' }}>{label}</div>
        <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', fontFamily: "'Share Tech Mono', monospace", marginTop: 2 }}>{detail}</div>
        <div style={{ fontSize: 10, marginTop: 4, fontFamily: "'Share Tech Mono', monospace", color: warn ? '#ff4444' : 'rgba(0,180,255,0.6)' }}>
          {warn ? '⚠ HIGH' : '● NOMINAL'}
        </div>
      </div>
    </div>
  );
};

// Waveform canvas
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

// CPU history graph
const CPUGraph: React.FC<{ history: number[]; current: number }> = ({ history, current }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    const W = canvas.offsetWidth * window.devicePixelRatio;
    const H = canvas.offsetHeight * window.devicePixelRatio;
    canvas.width = W; canvas.height = H;
    ctx.clearRect(0, 0, W, H);
    const step = W / (history.length - 1);
    ctx.beginPath();
    history.forEach((v, i) => {
      const x = i * step;
      const y = H - (v / 100) * H * 0.85 - H * 0.05;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.strokeStyle = 'rgba(0,180,255,0.8)';
    ctx.lineWidth = 1.5 * window.devicePixelRatio;
    ctx.stroke();
    ctx.lineTo(W, H); ctx.lineTo(0, H); ctx.closePath();
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, 'rgba(0,180,255,0.15)');
    grad.addColorStop(1, 'rgba(0,180,255,0)');
    ctx.fillStyle = grad;
    ctx.fill();
  }, [history]);

  return (
    <div style={{
      background: 'rgba(0,180,255,0.03)',
      border: '1px solid rgba(0,180,255,0.1)',
      borderRadius: 10, padding: '10px 12px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: 9, letterSpacing: '0.3em', color: 'rgba(0,180,255,0.4)', fontFamily: "'Share Tech Mono', monospace" }}>CPU HISTORY · 60S</span>
        <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)', fontFamily: "'Share Tech Mono', monospace" }}>{Math.round(current)}%</span>
      </div>
      <canvas ref={canvasRef} style={{ width: '100%', height: 48, display: 'block' }} />
    </div>
  );
};

// Settings panel — Clear Test Data button + future controls
const SettingsView: React.FC<{
  clearing: boolean;
  clearResult: string | null;
  onClear: () => void;
}> = ({ clearing, clearResult, onClear }) => (
  <div style={{ padding: '28px 24px', display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 460, margin: '0 auto', width: '100%' }}>
    {/* Header */}
    <div style={{ fontSize: 9, letterSpacing: '0.3em', color: 'rgba(0,180,255,0.4)', fontFamily: "'Share Tech Mono', monospace", paddingBottom: 10, borderBottom: '1px solid rgba(0,180,255,0.1)' }}>
      SETTINGS · SYSTEM CONFIG
    </div>

    {/* Data Management */}
    <div style={{ background: 'rgba(0,180,255,0.03)', border: '1px solid rgba(0,180,255,0.12)', borderRadius: 12, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.15em', color: 'rgba(255,255,255,0.7)' }}>DATA MANAGEMENT</div>
      <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', fontFamily: "'Share Tech Mono', monospace", lineHeight: 1.6 }}>
        Wipes all error records from the local SQLite database.<br />
        Use this to clear test data before a fresh monitoring session.<br />
        This action cannot be undone.
      </div>
      <button
        onClick={onClear}
        disabled={clearing}
        style={{
          alignSelf: 'flex-start',
          background: clearing ? 'rgba(255,68,68,0.06)' : 'rgba(255,68,68,0.08)',
          border: '1px solid rgba(255,68,68,0.35)',
          borderRadius: 8,
          color: '#ff4444',
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: '0.2em',
          padding: '8px 18px',
          cursor: clearing ? 'not-allowed' : 'pointer',
          fontFamily: "'Share Tech Mono', monospace",
          transition: 'all 0.2s',
          opacity: clearing ? 0.5 : 1,
        }}
        onMouseEnter={e => { if (!clearing) e.currentTarget.style.background = 'rgba(255,68,68,0.18)'; }}
        onMouseLeave={e => { if (!clearing) e.currentTarget.style.background = 'rgba(255,68,68,0.08)'; }}
      >
        {clearing ? '⟳  CLEARING...' : '⊘  CLEAR TEST DATA'}
      </button>
      {clearResult && (
        <div style={{
          fontSize: 10, fontFamily: "'Share Tech Mono', monospace", lineHeight: 1.4,
          color: clearResult.startsWith('✓') ? '#00ff96' : '#ff4444',
          padding: '6px 10px',
          background: clearResult.startsWith('✓') ? 'rgba(0,255,150,0.05)' : 'rgba(255,68,68,0.05)',
          border: `1px solid ${clearResult.startsWith('✓') ? 'rgba(0,255,150,0.2)' : 'rgba(255,68,68,0.2)'}`,
          borderRadius: 6,
        }}>
          {clearResult}
        </div>
      )}
    </div>

    {/* Version / info block */}
    <div style={{ background: 'rgba(0,180,255,0.02)', border: '1px solid rgba(0,180,255,0.08)', borderRadius: 12, padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.15em', color: 'rgba(255,255,255,0.5)' }}>SYSTEM INFO</div>
      {[
        ['API',       'http://localhost:5050'],
        ['WebSocket', 'ws://localhost:8765'],
        ['Dashboard', 'http://localhost:8081'],
        ['Version',   'JARVIS GUARDIAN v1.0'],
      ].map(([k, v]) => (
        <div key={k} style={{ display: 'flex', gap: 10, fontSize: 10, fontFamily: "'Share Tech Mono', monospace" }}>
          <span style={{ color: 'rgba(0,180,255,0.45)', minWidth: 72 }}>{k}</span>
          <span style={{ color: 'rgba(255,255,255,0.35)' }}>{v}</span>
        </div>
      ))}
    </div>
  </div>
);

export const OperatorHUD: React.FC<OperatorHUDProps> = ({
  vitals, projects, recentErrors, cpuHistory,
  activeView, onViewChange,
}) => {
  const { state: voiceState, lastResponse, manualWake } = useVoice();
  const [aiText, setAiText] = useState('All systems online. Say "Jarvis" or wave to activate voice command.');
  const [textVisible, setTextVisible] = useState(true);
  const [clock, setClock] = useState('');
  const [dateStr, setDateStr] = useState('');

  // Settings — Clear Test Data
  const [clearing, setClearing] = useState(false);
  const [clearResult, setClearResult] = useState<string | null>(null);

  const clearTestData = async () => {
    setClearing(true);
    setClearResult(null);
    try {
      const res = await fetch('http://localhost:5050/clear-errors', { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        setClearResult(`✓ Cleared ${data.deleted} error record${data.deleted !== 1 ? 's' : ''} from database`);
      } else {
        setClearResult(`✗ Failed: ${data.error || 'Unknown error'}`);
      }
    } catch {
      setClearResult('✗ Server unreachable — is the API running?');
    } finally {
      setClearing(false);
    }
  };

  // Clock
  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setClock(now.toLocaleTimeString('en-GB', { hour12: false }));
      setDateStr(now.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).toUpperCase());
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, []);

  // Fade text when speaking, reveal when done
  useEffect(() => {
    if (voiceState === 'speaking') {
      setTextVisible(false);
      setTimeout(() => {
        if (lastResponse) setAiText(lastResponse);
        setTextVisible(true);
      }, 1200);
    }
  }, [voiceState, lastResponse]);

  const navItems = [
    { id: 'dashboard', icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="1" y="1" width="6" height="6" rx="1"/><rect x="9" y="1" width="6" height="6" rx="1"/><rect x="1" y="9" width="6" height="6" rx="1"/><rect x="9" y="9" width="6" height="6" rx="1"/></svg>, label: 'HOME' },
    { id: 'projects', icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M2 4h12M2 8h8M2 12h10"/></svg>, label: 'PROJ' },
    { id: 'errors', icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M8 2L14 13H2L8 2z"/><path d="M8 7v3M8 11.5v.5"/></svg>, label: 'ERR' },
    { id: 'system', icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="8" cy="8" r="3"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.5 3.5l1.4 1.4M11.1 11.1l1.4 1.4M3.5 12.5l1.4-1.4M11.1 4.9l1.4-1.4"/></svg>, label: 'SYS' },
    { id: 'chat', icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M2 3h12v8H9l-3 2v-2H2z"/></svg>, label: 'AI' },
    { id: 'settings', icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 4h10M5 8h6M7 12h2"/><circle cx="5" cy="4" r="1.5" fill="currentColor" stroke="none" opacity=".7"/><circle cx="11" cy="8" r="1.5" fill="currentColor" stroke="none" opacity=".7"/><circle cx="9" cy="12" r="1.5" fill="currentColor" stroke="none" opacity=".7"/></svg>, label: 'SET' },
  ];

  // Smart timestamp: HH:MM for today, "DD Mon" for older entries
  const fmtErrorTime = (ts: string) => {
    const d = new Date(ts);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    return isToday
      ? d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
      : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
  };

  const statusColor = (s: Project['status']) =>
    s === 'healthy' ? '#00ff96' : s === 'error' ? '#ff4444' : s === 'fixing' ? '#ffaa00' : '#666';

  const sevColor = (s: string) => s === 'high' ? '#ff4444' : s === 'medium' ? '#ffaa00' : '#10b981';

  return (
    <>
      <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@400;700;900&family=Rajdhani:wght@400;600;700&display=swap" rel="stylesheet" />
      <div style={{
        display: 'grid',
        gridTemplateColumns: '52px 220px 1fr 300px',
        gridTemplateRows: '48px 1fr',
        height: '100vh',
        width: '100vw',
        background: '#030508',
        color: '#a8cce0',
        fontFamily: "'Rajdhani', sans-serif",
        overflow: 'hidden',
        position: 'fixed',
        inset: 0,
        zIndex: 1,
      }}>

        {/* Grid bg */}
        <div style={{
          position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0,
          backgroundImage: 'linear-gradient(rgba(0,180,255,0.025) 1px,transparent 1px),linear-gradient(90deg,rgba(0,180,255,0.025) 1px,transparent 1px)',
          backgroundSize: '40px 40px',
        }} />

        {/* TOPBAR */}
        <div style={{
          gridColumn: '1 / -1', gridRow: 1,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 20px',
          borderBottom: '1px solid rgba(0,180,255,0.12)',
          background: 'rgba(3,5,8,0.97)',
          backdropFilter: 'blur(10px)',
          zIndex: 10, position: 'relative',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 22, height: 22, borderRadius: '50%', border: '1px solid rgba(0,180,255,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#00b4ff', animation: 'pulseDot 2s ease-in-out infinite' }} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, fontWeight: 700, letterSpacing: '0.2em', color: '#00ff96' }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#00ff96', animation: 'pulseDot 1.5s ease-in-out infinite' }} />
              OPERATOR ONLINE
            </div>
          </div>
          <div style={{ position: 'absolute', left: '50%', transform: 'translateX(-50%)', textAlign: 'center' }}>
            <div style={{ fontSize: 11, letterSpacing: '0.3em', color: 'rgba(0,180,255,0.8)', fontFamily: "'Orbitron', sans-serif", fontWeight: 700 }}>
              JARVIS SYSTEM GUARDIAN <sup style={{ fontSize: 7, opacity: 0.6 }}>v1.0</sup>
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 14, fontWeight: 700, letterSpacing: '0.1em', color: 'rgba(255,255,255,0.85)', fontFamily: "'Share Tech Mono', monospace" }}>{clock}</div>
            <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', letterSpacing: '0.15em', fontFamily: "'Share Tech Mono', monospace" }}>{dateStr}</div>
          </div>
        </div>

        {/* NAV */}
        <div style={{
          gridColumn: 1, gridRow: 2,
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          padding: '16px 0', gap: 6,
          borderRight: '1px solid rgba(0,180,255,0.08)',
          background: 'rgba(3,5,8,0.8)', zIndex: 5,
        }}>
          {navItems.map(item => (
            <div key={item.id}
              onClick={() => onViewChange(item.id)}
              style={{
                width: 36, height: 36, display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center', gap: 2,
                borderRadius: 8, cursor: 'pointer', transition: 'all 0.2s',
                color: activeView === item.id ? 'rgba(0,180,255,0.9)' : 'rgba(255,255,255,0.2)',
                background: activeView === item.id ? 'rgba(0,180,255,0.08)' : 'transparent',
                border: activeView === item.id ? '1px solid rgba(0,180,255,0.2)' : '1px solid transparent',
                fontSize: 6, letterSpacing: '0.05em',
              }}
            >
              {item.icon}
              <span>{item.label}</span>
            </div>
          ))}
        </div>

        {/* LEFT GAUGES */}
        <div style={{
          gridColumn: 2, gridRow: 2,
          display: 'flex', flexDirection: 'column', gap: 10,
          padding: '16px 12px',
          borderRight: '1px solid rgba(0,180,255,0.08)',
          background: 'rgba(3,5,8,0.6)',
          overflowY: 'auto', zIndex: 5,
        }}>
          <ArcGauge value={vitals.cpu} label="CPU" detail="8-CORE AMD" color="#00b4ff" warn={vitals.cpu > 85} />
          <ArcGauge value={vitals.memory} label="RAM" detail={`${(vitals.ramUsedGB||0).toFixed(1)} / ${(vitals.ramTotalGB||0).toFixed(1)} GB`} color="#00b4ff" warn={vitals.memory > 85} />
          {vitals.hasTemperatures && vitals.tempCPU && (
            <ArcGauge value={vitals.tempCPU} max={100} label="CPU TEMP" detail="CELSIUS" color="#ffaa00" unit="°" warn={vitals.tempCPU > 80} />
          )}
          <ArcGauge value={vitals.diskCPercent || 0} label={vitals.diskCLabel || 'C:'} detail={`${(vitals.diskCUsedGB||0).toFixed(0)} / ${(vitals.diskCTotalGB||0).toFixed(0)} GB`} color="#ff6030" warn={(vitals.diskCPercent||0) > 85} />
          {(vitals.diskDTotalGB || 0) > 0 && (
            <ArcGauge value={vitals.diskDPercent || 0} label={vitals.diskDLabel || 'D:'} detail={`${(vitals.diskDUsedGB||0).toFixed(0)} / ${(vitals.diskDTotalGB||0).toFixed(0)} GB`} color="#00b4ff" />
          )}
          <CPUGraph history={cpuHistory} current={vitals.cpu} />
        </div>

        {/* ORB CENTRE / SETTINGS */}
        <div style={{
          gridColumn: 3, gridRow: 2,
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: activeView === 'settings' ? 'flex-start' : 'center',
          position: 'relative', overflow: activeView === 'settings' ? 'auto' : 'hidden', zIndex: 5,
        }}>

          {/* Settings view — rendered on top when active */}
          {activeView === 'settings' && (
            <SettingsView clearing={clearing} clearResult={clearResult} onClear={clearTestData} />
          )}

          {/* Orb + rings — always mounted to preserve Three.js state; hidden in settings */}
          <div style={{
            display: activeView === 'settings' ? 'none' : 'flex',
            flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            width: '100%', height: '100%', position: 'absolute', inset: 0,
          }}>
          {/* Rotating arc rings with project labels */}
          {projects.map((p, i) => {
            const sizes = [380, 430, 480];
            const durations = [12, 18, 25];
            const size = sizes[i] || 530;
            const dur = durations[i] || 30;
            return (
              <div key={p.id} style={{
                position: 'absolute',
                width: size, height: size,
                borderRadius: '50%',
                border: `1px solid ${statusColor(p.status)}30`,
                animation: `spin ${dur}s linear infinite ${i % 2 === 1 ? 'reverse' : ''}`,
                display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
              }}>
                {/* Glow arc */}
                <div style={{
                  position: 'absolute', inset: 0, borderRadius: '50%',
                  border: `2px solid transparent`,
                  borderTopColor: statusColor(p.status),
                  animation: `spin ${dur * 0.8}s linear infinite ${i % 2 === 1 ? 'reverse' : ''}`,
                  opacity: 0.7,
                }} />
                {/* Label at top of ring */}
                <div style={{
                  position: 'absolute', top: 4,
                  fontSize: 9, letterSpacing: '0.15em',
                  color: statusColor(p.status),
                  fontFamily: "'Share Tech Mono', monospace",
                  whiteSpace: 'nowrap',
                  textShadow: `0 0 8px ${statusColor(p.status)}`,
                }}>
                  {p.name.toUpperCase()} [{p.status.toUpperCase()}]
                </div>
              </div>
            );
          })}

          {/* Orb */}
          <div style={{ position: 'relative', zIndex: 2 }} onClick={() => manualWake()}>
            <Orb />
          </div>

          <div style={{
            marginTop: 16, fontSize: 9, letterSpacing: '0.35em',
            color: 'rgba(0,180,255,0.2)', fontFamily: "'Share Tech Mono', monospace",
            position: 'relative', zIndex: 2,
          }}>
            WAVE TO WAKE · SAY "JARVIS"
          </div>
          </div>{/* end orb wrapper */}
        </div>{/* end ORB CENTRE / SETTINGS */}

        {/* RIGHT PANEL */}
        <div style={{
          gridColumn: 4, gridRow: 2,
          display: 'flex', flexDirection: 'column',
          borderLeft: '1px solid rgba(0,180,255,0.12)',
          background: 'rgba(3,5,8,0.8)', zIndex: 5,
          overflow: 'hidden',
        }}>

          {/* AI Panel */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: 14, gap: 10, minHeight: 0 }}>
            <div style={{ fontSize: 9, letterSpacing: '0.3em', color: 'rgba(0,180,255,0.4)', fontFamily: "'Share Tech Mono', monospace", paddingBottom: 8, borderBottom: '1px solid rgba(0,180,255,0.1)' }}>
              AI · JARVIS RESPONSE
            </div>

            {/* Waveform */}
            <div style={{
              background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(0,180,255,0.1)',
              borderRadius: 8, padding: 10, height: 72, flexShrink: 0,
            }}>
              <Waveform active={voiceState === 'speaking' || voiceState === 'listening'} />
            </div>

            {/* Voice state indicator */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{
                width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                background: voiceState === 'listening' ? '#00ff96' : voiceState === 'speaking' ? '#9f00ff' : voiceState === 'thinking' ? '#ffaa00' : voiceState === 'hotword' as any ? '#00b4ff' : 'rgba(255,255,255,0.2)',
                boxShadow: voiceState !== 'idle' ? `0 0 6px currentColor` : 'none',
                animation: voiceState === 'listening' ? 'pulseDot 1s ease-in-out infinite' : 'none',
              }} />
              <span style={{ fontSize: 10, letterSpacing: '0.2em', color: 'rgba(255,255,255,0.4)', fontFamily: "'Share Tech Mono', monospace" }}>
                {voiceState === 'hotword' as any ? 'LISTENING FOR JARVIS...' : voiceState.toUpperCase()}
              </span>
            </div>

            {/* AI response text */}
            <div style={{
              flex: 1, background: 'rgba(0,0,0,0.2)',
              border: '1px solid rgba(0,180,255,0.08)', borderRadius: 8,
              padding: 12, overflowY: 'auto', minHeight: 0,
            }}>
              <div style={{ fontSize: 9, letterSpacing: '0.2em', color: '#00b4ff', fontFamily: "'Share Tech Mono', monospace", marginBottom: 8 }}>JARVIS ›</div>
              <div style={{
                fontSize: 13, lineHeight: 1.7, color: 'rgba(200,220,240,0.9)',
                opacity: textVisible ? 1 : 0,
                transition: 'opacity 0.8s ease',
              }}>
                {aiText}
              </div>
            </div>

            {/* Input */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(0,180,255,0.15)',
              borderRadius: 8, padding: '6px 10px',
            }}>
              <input
                type="text"
                placeholder="TYPE OR SAY JARVIS..."
                style={{
                  flex: 1, background: 'transparent', border: 'none', outline: 'none',
                  fontFamily: "'Share Tech Mono', monospace", fontSize: 11,
                  color: 'rgba(255,255,255,0.7)', letterSpacing: '0.05em',
                }}
              />
              <div style={{
                width: 24, height: 24, borderRadius: 4,
                background: 'rgba(0,180,255,0.15)', border: '1px solid rgba(0,180,255,0.3)',
                color: '#00b4ff', fontSize: 14, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>›</div>
            </div>
          </div>

          {/* Error feed */}
          <div style={{
            borderTop: '1px solid rgba(0,180,255,0.1)',
            padding: '10px 14px', maxHeight: 160, overflowY: 'auto', flexShrink: 0,
          }}>
            <div style={{ fontSize: 9, letterSpacing: '0.3em', color: 'rgba(255,80,80,0.5)', fontFamily: "'Share Tech Mono', monospace", marginBottom: 8 }}>
              REAL-TIME ERRORS
            </div>
            {recentErrors.slice(0, 4).map(err => (
              <div key={err.id} style={{ display: 'flex', gap: 6, alignItems: 'flex-start', marginBottom: 6 }}>
                <div style={{
                  fontSize: 8, letterSpacing: '0.1em', padding: '1px 4px', borderRadius: 3,
                  flexShrink: 0, marginTop: 1, fontFamily: "'Share Tech Mono', monospace",
                  background: `${sevColor(err.severity)}18`,
                  color: sevColor(err.severity),
                  border: `1px solid ${sevColor(err.severity)}40`,
                }}>
                  {err.severity === 'high' ? 'CRIT' : err.severity === 'medium' ? 'WARN' : 'INFO'}
                </div>
                <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)', fontFamily: "'Share Tech Mono', monospace", lineHeight: 1.4, flex: 1, minWidth: 0 }}>
                  {err.project_name} · {err.error_text.substring(0, 45)}
                </div>
                <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.2)', fontFamily: "'Share Tech Mono', monospace", flexShrink: 0 }}>
                  {fmtErrorTime(err.timestamp)}
                </div>
              </div>
            ))}
            {recentErrors.length === 0 && (
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.2)', fontFamily: "'Share Tech Mono', monospace" }}>No active errors</div>
            )}
          </div>

          {/* Camera HUD */}
          <div style={{
            borderTop: '1px solid rgba(0,180,255,0.1)',
            padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0,
          }}>
            <div style={{
              width: 72, height: 52, borderRadius: 6,
              background: 'rgba(0,0,0,0.5)', border: '1px solid rgba(0,180,255,0.2)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0, position: 'relative', overflow: 'hidden',
            }}>
              {/* Corner reticles */}
              {[['0','0','1px 0 0 1px'],['0','auto','1px 1px 0 0'],['auto','0','0 0 1px 1px'],['auto','auto','0 1px 1px 0']].map(([t,r,b],i) => (
                <div key={i} style={{
                  position: 'absolute', width: 8, height: 8,
                  top: t === 'auto' ? 'auto' : 3, right: r === 'auto' ? 3 : 'auto',
                  bottom: t === 'auto' ? 3 : 'auto', left: r === '0' ? 3 : 'auto',
                  border: `1px solid rgba(0,180,255,0.5)`,
                  borderRadius: b as string,
                }} />
              ))}
              <div style={{ width: 18, height: 18, borderRadius: '50%', border: '1px solid rgba(0,180,255,0.4)' }} />
            </div>
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.15em', color: 'rgba(255,255,255,0.5)' }}>HAND TRACKER</div>
              <div style={{ fontSize: 9, color: '#00ff96', fontFamily: "'Share Tech Mono', monospace", marginTop: 2 }}>✦ ACTIVE</div>
              <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.2)', fontFamily: "'Share Tech Mono', monospace" }}>WAVE TO WAKE</div>
            </div>
          </div>
        </div>

        <style>{`
          @keyframes pulseDot { 0%,100%{box-shadow:0 0 0 0 rgba(0,180,255,0.6)} 50%{box-shadow:0 0 0 4px rgba(0,180,255,0)} }
          @keyframes spin { to { transform: rotate(360deg); } }
          @keyframes orbBreathe { 0%,100%{box-shadow:0 0 30px rgba(0,180,255,0.15)} 50%{box-shadow:0 0 60px rgba(0,180,255,0.4)} }
          ::-webkit-scrollbar { width: 3px; }
          ::-webkit-scrollbar-track { background: transparent; }
          ::-webkit-scrollbar-thumb { background: rgba(0,180,255,0.2); border-radius: 2px; }
        `}</style>
      </div>
    </>
  );
};

export default OperatorHUD;