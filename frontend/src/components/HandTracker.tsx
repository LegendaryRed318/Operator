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
  const [handDetected, setHandDetected] = React.useState(false);

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
      await loadScripts();
      isInitialized.current = true;

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
            setHandDetected(true);
            const landmarks = results.multiHandLandmarks[0];
            // Log landmarks for debugging (remove in production)
            console.log('Hand landmarks detected', landmarks);
            const indexTip = landmarks[8];
            const middleTip = landmarks[12];
            const indexMCP = landmarks[5];
            const middleMCP = landmarks[9];
            const ringTip = landmarks[16];
            const ringMCP = landmarks[13];
            const pinkyTip = landmarks[20];
            const pinkyMCP = landmarks[17];

            const indexExtended = indexTip.y < indexMCP.y;
            const middleExtended = middleTip.y < middleMCP.y;
            const ringFolded = ringTip.y > ringMCP.y;
            const pinkyFolded = pinkyTip.y > pinkyMCP.y;

            if (indexExtended && middleExtended && ringFolded && pinkyFolded) {
              const now = Date.now();
              if (now - lastWave.current > 2000) {
                lastWave.current = now;
                onWave();
              }
            }
          } else {
            setHandDetected(false);
          }
        });

        if (videoRef.current) {
          // Request brighter exposure and higher resolution
          const stream = await navigator.mediaDevices.getUserMedia({
            video: {
              width: { ideal: 1280 },
              height: { ideal: 720 },
              exposureMode: 'continuous',
              exposureCompensation: 1.0,
            }
          });
          videoRef.current.srcObject = stream;
          await videoRef.current.play();

          const camera = new window.Camera(videoRef.current, {
            onFrame: async () => {
              await hands.send({ image: videoRef.current! });
            },
            width: 640,
            height: 480,
          });
          await camera.start();
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
    <div style={{ position: 'fixed', bottom: 10, right: 10, zIndex: 1000, opacity: 0.8, pointerEvents: 'none' }}>
      <video
        ref={videoRef}
        style={{
          width: '200px',
          borderRadius: '12px',
          border: handDetected ? '2px solid #00ffaa' : '2px solid #ff5555',
          filter: 'brightness(1.2) contrast(1.1)',
          boxShadow: '0 0 10px rgba(0,0,0,0.5)'
        }}
        autoPlay
        muted
        playsInline
      />
      <div style={{ textAlign: 'center', fontSize: '10px', marginTop: '4px', color: handDetected ? '#00ffaa' : '#ff5555' }}>
        {handDetected ? '✋ Hand detected' : '🖐️ No hand'}
      </div>
    </div>
  );
};

export default HandTracker;
