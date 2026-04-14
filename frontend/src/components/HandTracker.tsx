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

const HandTracker: React.FC<HandTrackerProps> = ({ onWave }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const handsRef = useRef<any>(null);
  const cameraRef = useRef<any>(null);
  const isInitialized = useRef(false);
  const lastWave = useRef(0);
  const handDetectedRef = useRef(false);

  useEffect(() => {
    if (isInitialized.current) return;

    const loadScripts = async () => {
      return new Promise((resolve) => {
        if (window.Hands && window.Camera) {
          resolve(true);
          return;
        }
        const script1 = document.createElement('script');
        script1.src = 'https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js';
        script1.onload = () => {
          const script2 = document.createElement('script');
          script2.src = 'https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js';
          script2.onload = () => resolve(true);
          document.body.appendChild(script2);
        };
        document.body.appendChild(script1);
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
          if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
            handDetectedRef.current = true;
            const landmarks = results.multiHandLandmarks[0];
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
          }
        });

        if (videoRef.current) {
          const camera = new window.Camera(videoRef.current, {
            onFrame: async () => {
              await hands.send({ image: videoRef.current! });
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
                  console.log('[HandTracker] Camera start interrupted — resetting for retry');
                  isInitialized.current = false;
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
      // No cleanup
    };
  }, [onWave]);

  return (
    <>
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
    </>
  );
};

export default HandTracker;
