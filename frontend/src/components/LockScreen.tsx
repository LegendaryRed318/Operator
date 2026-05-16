import React, { useState, useEffect, useRef } from 'react';

// Password is loaded from frontend/.env (VITE_LOCK_PASSWORD=yourcode)
// Never hardcode secrets here — they end up in the JS bundle.
const SECRET_PASSWORD = import.meta.env.VITE_LOCK_PASSWORD as string | undefined;
if (!SECRET_PASSWORD) {
  console.warn('[LockScreen] VITE_LOCK_PASSWORD is not set in .env — lock screen will reject all entries');
}

interface LockScreenProps {
  onUnlock: () => void;
}

export const LockScreen: React.FC<LockScreenProps> = ({ onUnlock }) => {
  const [input, setInput] = useState('');
  const [error, setError] = useState(false);
  const [shake, setShake] = useState(false);
  const [unlocking, setUnlocking] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    // If the env var is missing, fail closed — never accidentally unlock
    if (!SECRET_PASSWORD) {
      setError(true);
      setShake(true);
      setTimeout(() => setShake(false), 600);
      setTimeout(() => setError(false), 3000);
      return;
    }
    if (input === SECRET_PASSWORD) {
      setUnlocking(true);
      setTimeout(() => onUnlock(), 1200);
    } else {
      setError(true);
      setShake(true);
      setInput('');
      setTimeout(() => setShake(false), 600);
      setTimeout(() => setError(false), 2000);
    }
  };

  // handleKey removed since form submission handles Enter natively

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: '#050508',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      gap: '2rem',
      opacity: unlocking ? 0 : 1,
      transition: 'opacity 1s ease',
    }}>
      {/* Grid background */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: `linear-gradient(rgba(0,255,255,0.03) 1px, transparent 1px),
                          linear-gradient(90deg, rgba(0,255,255,0.03) 1px, transparent 1px)`,
        backgroundSize: '40px 40px',
      }} />

      {/* Glowing orb */}
      <div style={{
        width: 80, height: 80, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(0,255,255,0.6) 0%, rgba(0,255,255,0.1) 60%, transparent 100%)',
        boxShadow: '0 0 40px rgba(0,255,255,0.4), 0 0 80px rgba(0,255,255,0.2)',
        animation: 'pulse 2s ease-in-out infinite',
      }} />

      {/* Title */}
      <div style={{ textAlign: 'center', zIndex: 1 }}>
        <div style={{
          fontSize: '0.75rem', letterSpacing: '0.4em',
          color: 'rgba(0,255,255,0.6)', marginBottom: '0.5rem',
          textTransform: 'uppercase',
        }}>
          OPERATOR · JARVIS SYSTEM
        </div>
        <div style={{
          fontSize: '1.5rem', fontWeight: 700, letterSpacing: '0.15em',
          color: 'rgba(255,255,255,0.9)',
        }}>
          IDENTITY VERIFICATION
        </div>
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} style={{
        zIndex: 1, display: 'flex', flexDirection: 'column',
        alignItems: 'center', gap: '0.75rem',
        animation: shake ? 'shake 0.5s ease' : 'none',
      }}>
        <input
          ref={inputRef}
          type="password"
          autoComplete="current-password"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Enter access code"
          style={{
            background: 'rgba(0,255,255,0.05)',
            border: `1px solid ${error ? 'rgba(255,50,50,0.8)' : 'rgba(0,255,255,0.3)'}`,
            borderRadius: '4px',
            color: error ? 'rgba(255,100,100,0.9)' : 'rgba(0,255,255,0.9)',
            fontSize: '1rem', letterSpacing: '0.2em',
            padding: '0.75rem 1.5rem',
            textAlign: 'center', outline: 'none',
            width: '280px',
            transition: 'border-color 0.3s',
          }}
        />

        {error && (
          <div style={{ color: 'rgba(255,80,80,0.9)', fontSize: '0.75rem', letterSpacing: '0.15em' }}>
            ACCESS DENIED — INVALID CODE
          </div>
        )}

        <button
          onClick={handleSubmit}
          style={{
            background: 'rgba(0,255,255,0.1)',
            border: '1px solid rgba(0,255,255,0.4)',
            borderRadius: '4px',
            color: 'rgba(0,255,255,0.9)',
            fontSize: '0.8rem', letterSpacing: '0.25em',
            padding: '0.6rem 2rem', cursor: 'pointer',
            transition: 'all 0.2s',
          }}
          onMouseEnter={e => (e.currentTarget.style.background = 'rgba(0,255,255,0.2)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'rgba(0,255,255,0.1)')}
        >
          AUTHENTICATE
        </button>
      </form>

      <div style={{
        position: 'absolute', bottom: '2rem',
        fontSize: '0.65rem', letterSpacing: '0.2em',
        color: 'rgba(255,255,255,0.15)',
      }}>
        OPERATOR v1.0 · AUTHORISED PERSONNEL ONLY
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.08); opacity: 0.8; }
        }
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          20% { transform: translateX(-10px); }
          40% { transform: translateX(10px); }
          60% { transform: translateX(-8px); }
          80% { transform: translateX(8px); }
        }
      `}</style>
    </div>
  );
};
