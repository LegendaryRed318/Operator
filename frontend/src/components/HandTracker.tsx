import React, { useRef, useEffect } from 'react';
import { Hands, Results } from '@mediapipe/hands';
import { Camera } from '@mediapipe/camera_utils';

interface HandTrackerProps {
  onWave: () => void;
}

const HandTracker: React.FC<HandTrackerProps> = ({ onWave }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const handsRef = useRef<Hands | null>(null);
  const cameraRef = useRef<Camera | null>(null);
  const isInitialized = useRef(false);

  useEffect(() => {
    // Prevent multiple initializations
    if (isInitialized.current) return;
    isInitialized.current = true;

    const hands = new Hands({
      locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}` 
    });

    hands.setOptions({
      maxNumHands: 1,
      modelComplexity: 1,
      minDetectionConfidence: 0.5,
      minTrackingConfidence: 0.5
    });

    let lastWave = 0;

    const onResults = (results: Results) => {
      if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
        const landmarks = results.multiHandLandmarks[0];
        // Detect wave: index and middle fingers extended, ring and pinky folded
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
          if (now - lastWave > 2000) {
            lastWave = now;
            onWave();
          }
        }
      }
    };

    hands.onResults(onResults);

    // Initialize the WebGL context and start camera
    const start = async () => {
      if (videoRef.current) {
        try {
          const camera = new Camera(videoRef.current, {
            onFrame: async () => {
              try {
                await hands.send({ image: videoRef.current! });
              } catch (err) {
                // Silently ignore WebAssembly abort errors (do not reinitialize)
                if (err instanceof Error && err.message.includes('Aborted')) {
                  console.warn('[HandTracker] WebAssembly abort (ignored)');
                } else {
                  console.error('[HandTracker] Error during frame processing', err);
                }
              }
            },
            width: 640,
            height: 480
          });
          await camera.start();
          cameraRef.current = camera;
        } catch (err) {
          console.error('[HandTracker] Failed to start camera', err);
        }
      }
    };

    start();
    handsRef.current = hands;

    // No cleanup that closes or destroys the hands instance
    return () => {
      // Do NOT call hands.close() – it causes WebGL context loss.
      // The component will stay alive for the entire app lifetime.
      if (cameraRef.current) {
        // Camera can be stopped, but leaving it running is fine.
      }
    };
  }, [onWave]);

  return (
    <div style={{ position: 'fixed', bottom: 10, right: 10, zIndex: 1000, opacity: 0.3, pointerEvents: 'none' }}>
      <video ref={videoRef} style={{ width: '160px', borderRadius: '8px' }} autoPlay muted playsInline />
      <canvas ref={canvasRef} style={{ display: 'none' }} />
    </div>
  );
};

export default HandTracker;
