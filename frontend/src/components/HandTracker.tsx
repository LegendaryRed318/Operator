import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useVoice } from '../contexts/VoiceContext';

// MediaPipe types
interface HandLandmark {
  x: number;
  y: number;
  z: number;
}

interface HandResults {
  multiHandLandmarks?: HandLandmark[][];
}

type HandState = 'loading' | 'active' | 'error' | 'unavailable';

interface HandTrackerProps {
  onWaveDetected?: () => void;
  enabled?: boolean;
}

/**
 * Load a script from CDN and return a promise that resolves when loaded.
 */
function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    // Don't load twice
    if (document.querySelector(`script[src="${src}"]`)) {
      resolve();
      return;
    }
    const script = document.createElement('script');
    script.src = src;
    script.crossOrigin = 'anonymous';
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Failed to load script: ${src}`));
    document.head.appendChild(script);
  });
}

export const HandTracker: React.FC<HandTrackerProps> = ({ 
  onWaveDetected,
  enabled = true 
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [handState, setHandState] = useState<HandState>('loading');
  const [errorMessage, setErrorMessage] = useState('');
  const [showVideo, setShowVideo] = useState(false);
  
  const { manualWake, state: voiceState } = useVoice();
  
  // MediaPipe refs
  const handsRef = useRef<any>(null);
  const cameraRef = useRef<any>(null);
  
  // Gesture detection refs
  const previousWristX = useRef<number | null>(null);
  const waveCount = useRef(0);
  const lastWaveTime = useRef(0);
  const isWaveCooldown = useRef(false);
  
  // Detect wave gesture
  const detectWave = useCallback((landmarks: HandLandmark[]) => {
    const wrist = landmarks[0]; // Wrist landmark
    const now = Date.now();
    
    // Cooldown between waves (2 seconds)
    if (isWaveCooldown.current && now - lastWaveTime.current > 2000) {
      isWaveCooldown.current = false;
      waveCount.current = 0;
    }
    
    if (isWaveCooldown.current) return;
    
    if (previousWristX.current !== null) {
      const deltaX = wrist.x - previousWristX.current;
      
      // Detect significant horizontal movement
      if (Math.abs(deltaX) > 0.05) {
        waveCount.current++;
        
        // Wave detected after 3 significant movements
        if (waveCount.current >= 3) {
          console.log('[HandTracker] Wave gesture detected!');
          lastWaveTime.current = now;
          isWaveCooldown.current = true;
          waveCount.current = 0;
          
          // Trigger wake
          if (voiceState === 'idle') {
            manualWake();
            onWaveDetected?.();
          }
        }
      }
    }
    
    previousWristX.current = wrist.x;
  }, [manualWake, onWaveDetected, voiceState]);
  
  // Process hand detection results
  const onResults = useCallback((results: HandResults) => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    
    if (canvas && video) {
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
          const landmarks = results.multiHandLandmarks[0];
          drawHandConnections(ctx, landmarks);
          detectWave(landmarks);
        }
      }
    }
  }, [detectWave]);
  
  // Initialize MediaPipe Hands via CDN script tags
  useEffect(() => {
    if (!enabled) {
      setHandState('unavailable');
      return;
    }
    
    let isMounted = true;
    
    const initMediaPipe = async () => {
      try {
        // Load MediaPipe scripts from CDN (avoids all CommonJS/ESM bundling issues)
        await loadScript('https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js');
        await loadScript('https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js');
        
        if (!isMounted) return;
        
        // Access the global objects that the CDN scripts expose
        const win = window as any;
        
        if (!win.Hands) {
          throw new Error('MediaPipe Hands not found on window after loading CDN script');
        }
        if (!win.Camera) {
          throw new Error('MediaPipe Camera not found on window after loading CDN script');
        }
        
        // Create Hands instance using the global constructor
        const hands = new win.Hands({
          locateFile: (file: string) => {
            return `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`;
          }
        });
        
        hands.setOptions({
          maxNumHands: 1,
          modelComplexity: 1,
          minDetectionConfidence: 0.5,
          minTrackingConfidence: 0.5
        });
        
        hands.onResults(onResults);
        handsRef.current = hands;
        
        // Initialize camera
        if (videoRef.current) {
          const camera = new win.Camera(videoRef.current, {
            onFrame: async () => {
              if (handsRef.current && videoRef.current) {
                await handsRef.current.send({ image: videoRef.current });
              }
            },
            width: 320,
            height: 240
          });
          
          cameraRef.current = camera;
          
          try {
            await camera.start();
            if (isMounted) {
              setHandState('active');
              setShowVideo(true);
              console.log('[HandTracker] ✓ MediaPipe Hands initialized via CDN');
            }
          } catch (err) {
            console.error('[HandTracker] Camera error:', err);
            if (isMounted) {
              setHandState('error');
              setErrorMessage('Camera access denied or unavailable');
            }
          }
        }
      } catch (err) {
        console.error('[HandTracker] MediaPipe initialization error:', err);
        if (isMounted) {
          setHandState('error');
          setErrorMessage(`Failed to load hand tracking: ${(err as Error).message}`);
        }
      }
    };
    
    initMediaPipe();
    
    return () => {
      isMounted = false;
      if (cameraRef.current) {
        try { cameraRef.current.stop(); } catch (_) {}
      }
      if (handsRef.current) {
        try { handsRef.current.close(); } catch (_) {}
      }
    };
  }, [enabled, onResults]);
  
  // Draw hand skeleton
  const drawHandConnections = (ctx: CanvasRenderingContext2D, landmarks: HandLandmark[]) => {
    ctx.strokeStyle = '#00d4ff';
    ctx.lineWidth = 2;
    
    const connections = [
      [0, 1], [1, 2], [2, 3], [3, 4], // Thumb
      [0, 5], [5, 6], [6, 7], [7, 8], // Index finger
      [0, 9], [9, 10], [10, 11], [11, 12], // Middle finger
      [0, 13], [13, 14], [14, 15], [15, 16], // Ring finger
      [0, 17], [17, 18], [18, 19], [19, 20], // Pinky
      [0, 5], [5, 9], [9, 13], [13, 17] // Palm
    ];
    
    const width = canvasRef.current?.width || 320;
    const height = canvasRef.current?.height || 240;
    
    connections.forEach(([start, end]) => {
      const startPoint = landmarks[start];
      const endPoint = landmarks[end];
      
      ctx.beginPath();
      ctx.moveTo(startPoint.x * width, startPoint.y * height);
      ctx.lineTo(endPoint.x * width, endPoint.y * height);
      ctx.stroke();
    });
    
    landmarks.forEach((landmark, index) => {
      ctx.beginPath();
      ctx.arc(landmark.x * width, landmark.y * height, 4, 0, 2 * Math.PI);
      ctx.fillStyle = index === 0 ? '#ff0000' : '#00ff00';
      ctx.fill();
    });
  };
  
  const toggleVideo = () => {
    setShowVideo(prev => !prev);
  };
  
  if (!enabled) return null;
  
  return (
    <div className="hand-tracker" style={styles.container}>
      {/* Status indicator */}
      <div style={styles.statusBar}>
        <div style={{
          ...styles.statusDot,
          backgroundColor: handState === 'active' ? '#00ff00' : 
                          handState === 'loading' ? '#ffaa00' : '#ff0000'
        }} />
        <span style={styles.statusText}>
          {handState === 'active' ? 'Hand tracking active - wave to wake' : 
           handState === 'loading' ? 'Initializing hand tracking...' : 
           errorMessage || 'Hand tracking unavailable'}
        </span>
        <button onClick={toggleVideo} style={styles.toggleButton}>
          {showVideo ? 'Hide' : 'Show'} Camera
        </button>
      </div>
      
      {/* Hidden video element for MediaPipe */}
      <video
        ref={videoRef}
        style={{ display: 'none' }}
        playsInline
      />
      
      {/* Canvas for visualization */}
      {showVideo && handState === 'active' && (
        <canvas
          ref={canvasRef}
          width={320}
          height={240}
          style={styles.canvas}
        />
      )}
      
      <style>{`
        .hand-tracker {
          animation: fadeIn 0.3s ease;
        }
        
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
      `}</style>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    position: 'fixed',
    bottom: '20px',
    right: '20px',
    zIndex: 1000,
    background: 'rgba(10, 10, 18, 0.9)',
    border: '1px solid rgba(0, 212, 255, 0.3)',
    borderRadius: '12px',
    padding: '12px',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    minWidth: '200px',
  },
  statusBar: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  statusDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    transition: 'background-color 0.3s ease',
  },
  statusText: {
    fontSize: '0.75rem',
    color: 'rgba(255, 255, 255, 0.8)',
    flex: 1,
  },
  toggleButton: {
    fontSize: '0.7rem',
    padding: '4px 8px',
    background: 'rgba(0, 212, 255, 0.2)',
    border: '1px solid rgba(0, 212, 255, 0.4)',
    borderRadius: '4px',
    color: '#00d4ff',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  canvas: {
    borderRadius: '8px',
    border: '1px solid rgba(0, 212, 255, 0.2)',
    width: '100%',
    height: 'auto',
  },
};

export default HandTracker;
