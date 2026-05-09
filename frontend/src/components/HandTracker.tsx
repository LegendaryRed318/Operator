import React, { useRef, useEffect } from 'react';

interface HandTrackerProps {
  onWave: () => void;
}

declare global {
  interface Window {
    Hands: any;
    Camera: any;
    FaceDetection: any;
  }
}

interface MediaPipeResults {
  multiHandLandmarks: Array<Array<{ x: number; y: number; z: number }>>;
}

interface FaceDetectionResults {
  detections: Array<any>;
}

const ABSENCE_TIMEOUT = 60000; // 60 seconds of absence before re-triggering "Welcome"

const HandTracker: React.FC<HandTrackerProps> = ({ onWave }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const handsRef = useRef<any>(null);
  const faceDetectionRef = useRef<any>(null);
  const cameraRef = useRef<any>(null);
  const isInitialized = useRef(false);
  const lastWave = useRef(0);
  const frameErrorLogged = useRef(false);
  
  const handDetectedRef = useRef(false);
  const [handDetected, setHandDetected] = React.useState(false);
  
  const faceDetectedRef = useRef(false);
  const [faceDetected, setFaceDetected] = React.useState(false);
  const lastFaceSeen = useRef(0);

  useEffect(() => {
    if (isInitialized.current) {
      console.log('[HandTracker] Already initialized, skipping');
      return;
    }
    isInitialized.current = true;

    const loadScripts = (): Promise<void> => {
      return new Promise((resolve) => {
        if (window.Hands && window.Camera && window.FaceDetection) {
          resolve();
          return;
        }

        const existing1 = document.querySelector('script[src*="@mediapipe/hands/hands.js"]');
        const existing2 = document.querySelector('script[src*="@mediapipe/camera_utils"]');
        const existing3 = document.querySelector('script[src*="@mediapipe/face_detection"]');

        if (existing1 && existing2 && existing3) {
          const poll = setInterval(() => {
            if (window.Hands && window.Camera && window.FaceDetection) {
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
          script2.onload = () => {
            const script3 = document.createElement('script');
            script3.src = 'https://cdn.jsdelivr.net/npm/@mediapipe/face_detection/face_detection.js';
            script3.crossOrigin = 'anonymous';
            script3.onload = () => resolve();
            script3.onerror = () => resolve();
            document.body.appendChild(script3);
          };
          script2.onerror = () => resolve();
          document.body.appendChild(script2);
        };
        script1.onerror = () => resolve();
        document.body.appendChild(script1);
      });
    };

    const initVision = async () => {
      await loadScripts();

      if (!videoRef.current) return;
      if (!window.Hands || !window.Camera || !window.FaceDetection) {
        console.error('[VisionTracker] MediaPipe scripts failed to load');
        return;
      }

      try {
        // Init Hands
        const hands = new window.Hands({
          locateFile: (file: string) =>
            `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`,
        });

        hands.setOptions({
          maxNumHands: 1,
          modelComplexity: 1,
          minDetectionConfidence: 0.5,
          minTrackingConfidence: 0.5,
        });

        hands.onResults((results: MediaPipeResults) => {
          if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
            setHandDetected(true);
            handDetectedRef.current = true;
            const landmarks = results.multiHandLandmarks[0];

            const indexExtended = landmarks[8].y < landmarks[5].y - 0.04;
            const middleExtended = landmarks[12].y < landmarks[9].y - 0.04;
            const ringExtended = landmarks[16].y < landmarks[13].y - 0.04;
            const pinkyExtended = landmarks[20].y < landmarks[17].y - 0.04;

            const fingersUp = [indexExtended, middleExtended, ringExtended, pinkyExtended].filter(Boolean).length;

            if (fingersUp >= 3) {
              const now = Date.now();
              if (now - lastWave.current > 5000) {
                setTimeout(() => {
                  if (handDetectedRef.current && lastWave.current < now) {
                    lastWave.current = Date.now();
                    console.log('[VisionTracker] WAVE FIRED');
                    onWaveRef.current();
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

        // Init Face Detection
        const faceDetection = new window.FaceDetection({
          locateFile: (file: string) =>
            `https://cdn.jsdelivr.net/npm/@mediapipe/face_detection/${file}`,
        });

        faceDetection.setOptions({
          model: 'short',
          minDetectionConfidence: 0.5,
        });

        faceDetection.onResults((results: FaceDetectionResults) => {
          const now = Date.now();
          const faceFound = results.detections && results.detections.length > 0;

          if (faceFound) {
            if (!faceDetectedRef.current) {
              const timeAwayMs = now - (lastFaceSeen.current || now);
              const timeAwaySec = timeAwayMs / 1000;
              console.log(`[VisionTracker] Face detected! (Away for ${timeAwaySec.toFixed(1)}s)`);
              
              if (lastFaceSeen.current !== 0) {
                window.dispatchEvent(new CustomEvent('vision:event', { 
                  detail: { 
                    event: 'face_detected', 
                    data: { new_arrival: timeAwayMs > ABSENCE_TIMEOUT, time_away: timeAwaySec } 
                  } 
                }));
              }
              
              faceDetectedRef.current = true;
              setFaceDetected(true);
            }
            lastFaceSeen.current = now;
          } else {
            if (faceDetectedRef.current && (now - lastFaceSeen.current > 5000)) {
              console.log('[VisionTracker] Person left the camera area');
              faceDetectedRef.current = false;
              setFaceDetected(false);
              
              window.dispatchEvent(new CustomEvent('vision:event', { 
                detail: { 
                  event: 'face_lost', 
                  data: { duration: (now - lastFaceSeen.current) / 1000 } 
                } 
              }));
            }
          }
        });

        faceDetectionRef.current = faceDetection;

        const camera = new window.Camera(videoRef.current, {
          onFrame: async () => {
            if (!videoRef.current) return;
            try {
              if (handsRef.current) await handsRef.current.send({ image: videoRef.current });
              if (faceDetectionRef.current) await faceDetectionRef.current.send({ image: videoRef.current });
            } catch (err) {
              if (!frameErrorLogged.current) {
                console.warn('[VisionTracker] Frame processing error (suppressed after first)');
                frameErrorLogged.current = true;
              }
            }
          },
          width: 640,
          height: 480,
        });

        cameraRef.current = camera;

        try {
          await camera.start();
          console.log('[VisionTracker] Camera started successfully');
        } catch (err: any) {
          if (err.name === 'AbortError') {
            console.warn('[VisionTracker] AbortError on camera start — ignoring');
          } else {
            console.error('[VisionTracker] Camera start failed:', err);
          }
        }

      } catch (err) {
        console.error('[VisionTracker] Failed to initialize MediaPipe:', err);
        isInitialized.current = false;
      }
    };

    initVision();

    return () => {
      if (cameraRef.current) {
        try { cameraRef.current.stop(); } catch (e) {}
      }
      if (handsRef.current) {
        try { handsRef.current.close(); } catch (e) {}
      }
      if (faceDetectionRef.current) {
        try { faceDetectionRef.current.close(); } catch (e) {}
      }
    };
  }, []);

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
      display: 'flex',
      flexDirection: 'column',
      gap: '4px',
      alignItems: 'flex-end',
    }}>
      <video
        ref={videoRef}
        style={{ width: '1px', height: '1px', opacity: 0, position: 'absolute' }}
        autoPlay muted playsInline
      />
      <div style={{
        fontSize: '11px',
        color: faceDetected ? '#00ffaa' : 'rgba(255,255,255,0.5)',
        fontFamily: 'monospace',
        letterSpacing: '0.1em',
        textAlign: 'right',
        background: 'rgba(0,0,0,0.3)',
        padding: '4px 8px',
        borderRadius: '4px',
        backdropFilter: 'blur(4px)',
      }}>
        {faceDetected ? '✦ FACE DETECTED' : '○ NO FACE'}
      </div>
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
