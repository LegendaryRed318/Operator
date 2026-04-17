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

export const OperatorHUD: React.FC<OperatorHUDProps> = ({ vitals, activeModel = 'qwen2.5-coder' }) => {
  const { state: voiceState, lastResponse, manualWake } = useVoice();
  const [aiText, setAiText] = useState('Good evening, sir. JARVIS online. How may I assist you today?');
  const [clock, setClock] = useState('');
  const sleeping = false; // TODO: wire to sleep manager
  const inputRef = React.useRef<HTMLInputElement>(null);

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
            {activeModel}
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
        </div>

        {/* ORB CENTRE */}
        <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', zIndex: 2 }}>
          <div style={{ transform: 'scale(1.8)', transition: 'transform 0.5s ease' }}>
            <Orb />
          </div>
          <div style={{ marginTop: 120, fontSize: 16, color: 'rgba(200,220,240,0.9)', maxWidth: 600, textAlign: 'center', lineHeight: 1.5 }}>
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
              onKeyDown={(e) => {
                if (e.key === 'Enter' && inputRef.current && inputRef.current.value.trim()) {
                  inputRef.current.value = '';
                }
              }}
              style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', color: '#fff', fontSize: 14, fontFamily: "'Share Tech Mono', monospace" }}
            />
            <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'rgba(0,180,255,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#00b4ff' }} onClick={manualWake}> microphone</div>
          </div>
        </div>
      </div>
    </>
  );
};

export default OperatorHUD;