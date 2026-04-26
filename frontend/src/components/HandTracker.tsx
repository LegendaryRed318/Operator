import React, { useRef, useEffect } from 'react';

interface HandTrackerProps {
  onWave: () => void;
}

declare global {
  interface Window {
    Hands: any;
    Camera: any;
  }
}

interface MediaPipeResults {
  multiHandLandmarks: Array<Array<{ x: number; y: number; z: number }>>;
}

const HandTracker: React.FC<HandTrackerProps> = ({ onWave }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const handsRef = useRef<any>(null);
  const cameraRef = useRef<any>(null);
  const isInitialized = useRef(false);  // MUST be module-level ref, not state
  const lastWave = useRef(0);
  const frameErrorLogged = useRef(false);
  const handDetectedRef = useRef(false);
  const [handDetected, setHandDetected] = React.useState(false);

  useEffect(() => {
    // CRITICAL: Set this SYNCHRONOUSLY before ANY async work
    // This prevents React Strict Mode double-mount from initialising twice
    if (isInitialized.current) {
      console.log('[HandTracker] Already initialized, skipping');
      return;
    }
    isInitialized.current = true;

    const loadScripts = (): Promise<void> => {
      return new Promise((resolve) => {
        if (window.Hands && window.Camera) {
          resolve();
          return;
        }

        // Check if scripts already loading (another instance may have started)
        const existing1 = document.querySelector('script[src*="@mediapipe/hands/hands.js"]');
        const existing2 = document.querySelector('script[src*="@mediapipe/camera_utils"]');

        if (existing1 && existing2) {
          // Scripts exist but window.Hands may not be ready yet — poll
          const poll = setInterval(() => {
            if (window.Hands && window.Camera) {
              clearInterval(poll);
              resolve();
            }
          }, 100);
          return;
        }

        const script1 = document.createElement('script');
        script1.src = 'https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js';
        script1.crossOrigin = 'anonymous';
        script1.onload = () => {
          const script2 = document.createElement('script');
          script2.src = 'https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js';
          script2.crossOrigin = 'anonymous';
          script2.onload = () => resolve();
          script2.onerror = () => resolve(); // Don't block on error
          document.body.appendChild(script2);
        };
        script1.onerror = () => resolve();
        document.body.appendChild(script1);
      });
    };

    const initHands = async () => {
      await loadScripts();

      if (!videoRef.current) return;
      if (!window.Hands || !window.Camera) {
        console.error('[HandTracker] MediaPipe scripts failed to load');
        return;
      }

      try {
        const hands = new window.Hands({
          locateFile: (file: string) =>
            `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`,
        });

        hands.setOptions({
          maxNumHands: 1,
          modelComplexity: 1, // Use 1 (full) for better accuracy
          minDetectionConfidence: 0.5, // Lower threshold for better detection
          minTrackingConfidence: 0.5,
        });

        hands.onResults((results: MediaPipeResults) => {
          if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
            setHandDetected(true);
            handDetectedRef.current = true;
            const landmarks = results.multiHandLandmarks[0];

            const indexTip = landmarks[8];
            const middleTip = landmarks[12];
            const indexMCP = landmarks[5];
            const middleMCP = landmarks[9];
            const ringTip = landmarks[16];
            const ringMCP = landmarks[13];
            const pinkyTip = landmarks[20];
            const pinkyMCP = landmarks[17];

            const indexExtended = indexTip.y < indexMCP.y - 0.04;
            const middleExtended = middleTip.y < middleMCP.y - 0.04;
            const ringExtended = ringTip.y < ringMCP.y - 0.04;
            const pinkyExtended = pinkyTip.y < pinkyMCP.y - 0.04;

            const fingersUp = [indexExtended, middleExtended, ringExtended, pinkyExtended]
              .filter(Boolean).length;

            // Wave detection with debounce (500ms hold required)
            if (fingersUp >= 3) {
              const now = Date.now();
              // 5s cooldown between waves
              if (now - lastWave.current > 5000) {
                // Require gesture to be held for 500ms before firing
                setTimeout(() => {
                  // Re-check if hand is still present and gesture still valid
                  if (handDetectedRef.current && lastWave.current < now) {
                    lastWave.current = Date.now();
                    console.log('[HandTracker] WAVE FIRED - fingers up:', fingersUp);
                    onWave();
                  }
                }, 500);
              }
            }
          } else {
            handDetectedRef.current = false;
            setHandDetected(false);
          }
        });

        handsRef.current = hands;

        // Use Camera utility — it handles the video stream internally
        // Do NOT call getUserMedia separately — it conflicts
        const camera = new window.Camera(videoRef.current, {
          onFrame: async () => {
            if (!handsRef.current || !videoRef.current) return;
            try {
              await handsRef.current.send({ image: videoRef.current });
            } catch (err) {
              if (!frameErrorLogged.current) {
                console.warn('[HandTracker] Frame processing error (suppressed after first)');
                frameErrorLogged.current = true;
              }
            }
          },
          width: 640,
          height: 480,
        });

        cameraRef.current = camera;

        // Start camera — handle AbortError gracefully
        try {
          await camera.start();
          console.log('[HandTracker] Camera started successfully');
        } catch (err: any) {
          if (err.name === 'AbortError') {
            console.warn('[HandTracker] AbortError on camera start — this is normal in Strict Mode, ignoring');
            // Don't reset isInitialized — let it stay true to prevent retry loop
          } else {
            console.error('[HandTracker] Camera start failed:', err);
          }
        }

      } catch (err) {
        console.error('[HandTracker] Failed to initialize MediaPipe Hands:', err);
        // Only reset if it's a real failure, not AbortError
        isInitialized.current = false;
      }
    };

    initHands();

    // Cleanup: Stop camera on unmount and close MediaPipe
    return () => {
      if (cameraRef.current) {
        try {
          cameraRef.current.stop();
          console.log('[HandTracker] Camera stopped on unmount');
        } catch (e) {
          // Ignore cleanup errors
        }
      }
      // Close MediaPipe Hands to release WebGL context
      if (handsRef.current) {
        try {
          handsRef.current.close();
          console.log('[HandTracker] MediaPipe Hands closed on unmount');
        } catch (e) {
          // Ignore cleanup errors
        }
      }
    };
  }, []); // Empty deps — run ONCE only. onWave handled via ref below.

  // Keep onWave in a ref so the gesture handler always has the latest version
  // without causing the useEffect to re-run
  const onWaveRef = useRef(onWave);
  useEffect(() => {
    onWaveRef.current = onWave;
  }, [onWave]);

  return (
    <div style={{
      position: 'fixed',
      bottom: 10,
      right: 10,
      zIndex: 1000,
      pointerEvents: 'none',
    }}>
      {/* Hidden video — MediaPipe needs it in DOM but we don't show it */}
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
      {/* Hand detection status - bottom right corner */}
      <div style={{
        fontSize: '11px',
        color: handDetected ? '#00ffaa' : 'rgba(255,255,255,0.5)',
        fontFamily: 'monospace',
        letterSpacing: '0.1em',
        textAlign: 'right',
        background: 'rgba(0,0,0,0.3)',
        padding: '4px 8px',
        borderRadius: '4px',
        backdropFilter: 'blur(4px)',
      }}>
        {handDetected ? '✦ HAND DETECTED' : '○ NO HAND'}
      </div>
    </div>
  );
};

export default HandTracker;
