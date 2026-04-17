import React, { useRef, useEffect, useState } from 'react';

interface HandTrackerProps {
  onWave: () => void;
}

declare global {
  interface Window {
    Hands: any;
    Camera: any;
  }
}

const HandTracker: React.FC<HandTrackerProps> = ({ onWave }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const handsRef = useRef<any>(null);
  const cameraRef = useRef<any>(null);
  const isInitialized = useRef(false);
  const isUnmounted = useRef(false);
  const lastWave = useRef(0);
  const handDetectedRef = useRef(false);
  const frameErrorLogged = useRef(false);
  const [handDetected, setHandDetected] = useState(false);

  useEffect(() => {
    isUnmounted.current = false;
    if (isInitialized.current) return;

        const loadScripts = async () => {
      return new Promise((resolve) => {
        if (window.Hands && window.Camera) {
          resolve(true);
          return;
        }

        const checkReady = () => {
          if (window.Hands && window.Camera) resolve(true);
          else setTimeout(checkReady, 100);
        };

        let script1 = document.querySelector('script[src*="hands.js"]') as HTMLScriptElement;
        if (!script1) {
          script1 = document.createElement('script');
          script1.src = 'https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js';
          document.head.appendChild(script1);
        }

        let script2 = document.querySelector('script[src*="camera_utils.js"]') as HTMLScriptElement;
        if (!script2) {
          script2 = document.createElement('script');
          script2.src = 'https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js';
          document.head.appendChild(script2);
        }

        checkReady();
      });
    };

    const initHands = async () => {
      // Guard must be set before any async work so Strict Mode's second mount
      // is blocked immediately, not after scripts have already started loading.
      isInitialized.current = true;
      await loadScripts();

      try {
        const hands = new window.Hands({
          locateFile: (file: string) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`,
        });

        hands.setOptions({
          maxNumHands: 1,
          modelComplexity: 1,
          minDetectionConfidence: 0.7,
          minTrackingConfidence: 0.7,
        });

        hands.onResults((results: any) => {
          const canvas = canvasRef.current;
          const ctx = canvas?.getContext('2d');
          
          if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
            handDetectedRef.current = true;
            setHandDetected(true);
            
            // Draw hand skeleton on canvas
            if (canvas && ctx && videoRef.current) {
              // Match canvas size to video
              canvas.width = videoRef.current.videoWidth || 320;
              canvas.height = videoRef.current.videoHeight || 240;
              
              ctx.clearRect(0, 0, canvas.width, canvas.height);
              
              const landmarks = results.multiHandLandmarks[0];
              
              // Set glow effect
              ctx.shadowColor = '#00d4ff';
              ctx.shadowBlur = 10;
              
              // Draw connections
              ctx.strokeStyle = '#00d4ff';
              ctx.lineWidth = 3;
              
              const connections = [
                [0, 1], [1, 2], [2, 3], [3, 4],  // Thumb
                [0, 5], [5, 6], [6, 7], [7, 8],  // Index
                [0, 9], [9, 10], [10, 11], [11, 12],  // Middle
                [0, 13], [13, 14], [14, 15], [15, 16],  // Ring
                [0, 17], [17, 18], [18, 19], [19, 20],  // Pinky
              ];
              
              connections.forEach(([start, end]) => {
                const startPt = landmarks[start];
                const endPt = landmarks[end];
                ctx.beginPath();
                ctx.moveTo(startPt.x * canvas.width, startPt.y * canvas.height);
                ctx.lineTo(endPt.x * canvas.width, endPt.y * canvas.height);
                ctx.stroke();
              });
              
              // Draw landmarks
              ctx.fillStyle = '#00d4ff';
              landmarks.forEach((lm: any) => {
                ctx.beginPath();
                ctx.arc(lm.x * canvas.width, lm.y * canvas.height, 6, 0, 2 * Math.PI);
                ctx.fill();
              });
            }
            
            const landmarks = results.multiHandLandmarks[0];
            
            // Process wave gesture
            const indexTip = landmarks[8];
            const middleTip = landmarks[12];
            const ringTip = landmarks[16];
            const pinkyTip = landmarks[20];
            const indexMCP = landmarks[5];
            const middleMCP = landmarks[9];
            const ringMCP = landmarks[13];
            const pinkyMCP = landmarks[17];

            // Open palm: at least 3 fingers extended
            const indexExtended = indexTip.y < indexMCP.y - 0.04;
            const middleExtended = middleTip.y < middleMCP.y - 0.04;
            const ringExtended = ringTip.y < ringMCP.y - 0.04;
            const pinkyExtended = pinkyTip.y < pinkyMCP.y - 0.04;

            const fingersUp = [indexExtended, middleExtended, ringExtended, pinkyExtended]
              .filter(Boolean).length;

            if (fingersUp >= 3) {
              const now = Date.now();
              if (now - lastWave.current > 2500) {
                lastWave.current = now;
                console.log('[HandTracker] WAVE FIRED - fingers up:', fingersUp);
                onWave();
              }
            }
          } else {
            handDetectedRef.current = false;
            setHandDetected(false);
            // Clear canvas when no hand detected
            if (canvas && ctx) {
              ctx.clearRect(0, 0, canvas.width, canvas.height);
            }
          }
        });

        if (videoRef.current) {
          const camera = new window.Camera(videoRef.current, {
            onFrame: async () => {
              if (isUnmounted.current || !handsRef.current) return;
              try {
                await handsRef.current.send({ image: videoRef.current! });
              } catch (e) {
                // Only log first error to prevent console spam
                if (!frameErrorLogged.current) {
                  console.warn('[HandTracker] Frame processing error (suppressed after first)');
                  frameErrorLogged.current = true;
                }
              }
            },
            // MediaPipe Camera manages getUserMedia + play() internally;
            // do NOT call videoRef.current.play() manually — that races
            // with Camera's own setup and causes the AbortError.
            width: 1280,
            height: 720,
          });

          const startPromise = camera.start();
          if (startPromise !== undefined) {
            startPromise
              .then(() => {
                console.log('[HandTracker] Camera started successfully');
              })
              .catch((error: Error) => {
                if (error.name === 'AbortError') {
                  console.log('[HandTracker] Camera start interrupted — will retry in 3s');
                  setTimeout(() => { isInitialized.current = false; }, 3000);
                } else {
                  console.error('[HandTracker] Camera error:', error);
                }
              });
          }

          cameraRef.current = camera;
        }

        handsRef.current = hands;
      } catch (err) {
        console.error('Failed to initialize MediaPipe Hands:', err);
      }
    };

    initHands();

    return () => {
      isUnmounted.current = true;
      // Cleanup MediaPipe tracks to prevent memory leaks and zombie webcam
      if (cameraRef.current) {
        try { cameraRef.current.stop(); } catch (e) { console.error('Camera stop error:', e); }
      }
      if (handsRef.current) {
        try { handsRef.current.close(); } catch (e) { console.error('Hands close error:', e); }
        handsRef.current = null;
      }
      isInitialized.current = false;
    };
  }, [onWave]);

  return (
    <div style={{ position: 'fixed', bottom: 10, right: 10, zIndex: 1000 }}>
      {/* Hand detection badge */}
      <div
        style={{
          position: 'absolute',
          top: -25,
          left: 0,
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
          padding: '4px 8px',
          background: handDetected ? 'rgba(0, 255, 0, 0.2)' : 'rgba(128, 128, 128, 0.2)',
          border: `1px solid ${handDetected ? '#00ff00' : '#888'}`,
          borderRadius: '4px',
          fontSize: '11px',
          color: handDetected ? '#00ff00' : '#888',
          fontFamily: 'JetBrains Mono, monospace',
          transition: 'all 0.2s ease',
        }}
      >
        <span>{handDetected ? '●' : '○'}</span>
        <span>{handDetected ? 'Hand detected' : 'No hand'}</span>
      </div>
      
      {/* Video element (hidden) */}
      <video
        ref={videoRef}
        style={{
          width: '1px',
          height: '1px',
          opacity: 0,
          position: 'absolute',
          pointerEvents: 'none',
        }}
        autoPlay
        muted
        playsInline
      />
      
      {/* Canvas overlay with hand skeleton */}
      <canvas
        ref={canvasRef}
        width={320}
        height={240}
        style={{
          width: '160px',
          height: '120px',
          borderRadius: '8px',
          border: '1px solid rgba(0, 212, 255, 0.3)',
          background: 'rgba(0, 0, 0, 0.5)',
          opacity: 1.0,
        }}
      />
    </div>
  );
};

export default HandTracker;
