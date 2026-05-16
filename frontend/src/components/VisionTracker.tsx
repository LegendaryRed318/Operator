import React, { useRef, useEffect, useState } from 'react';

interface VisionTrackerProps {
  onWave: () => void;
}

declare global {
  interface Window {
    Hands: any;
    Camera: any;
    FaceMesh: any;
  }
}

interface HandResults {
  multiHandLandmarks?: Array<Array<{ x: number; y: number; z: number }>>;
}

interface FaceMeshResults {
  multiFaceLandmarks?: Array<Array<{ x: number; y: number; z: number }>>;
}

interface KnownFace {
  label: string;
  embedding: [number, number, number];
}

const ABSENCE_TIMEOUT = 60000;
const REGISTRATION_SAMPLES = 5;
const KNOWN_FACE_KEY = 'jarvis_face_embedding';
const FACE_DISTANCE_THRESHOLD = 0.08;

const loadKnownFace = (): KnownFace | null => {
  try {
    const saved = localStorage.getItem(KNOWN_FACE_KEY);
    if (!saved) return null;
    const parsed = JSON.parse(saved) as KnownFace;
    if (parsed?.label && Array.isArray(parsed.embedding) && parsed.embedding.length === 3) {
      return { label: parsed.label, embedding: [parsed.embedding[0], parsed.embedding[1], parsed.embedding[2]] };
    }
  } catch {
    // ignore invalid storage
  }
  return null;
};

const saveKnownFace = (face: KnownFace) => {
  localStorage.setItem(KNOWN_FACE_KEY, JSON.stringify(face));
};

const averageEmbedding = (landmarks: Array<{ x: number; y: number; z: number }>) => {
  let sumX = 0;
  let sumY = 0;
  let sumZ = 0;
  for (const point of landmarks) {
    sumX += point.x;
    sumY += point.y;
    sumZ += point.z;
  }
  return [sumX / landmarks.length, sumY / landmarks.length, sumZ / landmarks.length] as [number, number, number];
};

const averageEmbeddings = (embeddings: Array<[number, number, number]>) => {
  const result: [number, number, number] = [0, 0, 0];
  for (const embedding of embeddings) {
    result[0] += embedding[0];
    result[1] += embedding[1];
    result[2] += embedding[2];
  }
  return [result[0] / embeddings.length, result[1] / embeddings.length, result[2] / embeddings.length] as [number, number, number];
};

const computeDistance = (a: [number, number, number], b: [number, number, number]) => {
  return Math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2);
};

const sendVisionEvent = (event: string, data: any = {}) => {
  const detail = { event, data };
  window.dispatchEvent(new CustomEvent('vision:event', { detail }));
};

const createFaceRecognitionDetail = (recognized: boolean, label: string, confidence: number) => ({
  recognized,
  label,
  confidence,
  timestamp: Date.now(),
});

const VisionTracker: React.FC<VisionTrackerProps> = ({ onWave }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const handsRef = useRef<any>(null);
  const faceMeshRef = useRef<any>(null);
  const cameraRef = useRef<any>(null);
  const isInitialized = useRef(false);
  const lastWave = useRef(0);
  const frameErrorLogged = useRef(false);
  const faceDetectedRef = useRef(false);
  const [faceDetected, setFaceDetected] = useState(false);
  const [faceRecognitionStatus, setFaceRecognitionStatus] = useState('Unknown Person');
  const [faceConfidence, setFaceConfidence] = useState<number | null>(null);
  const [registering, setRegistering] = useState(false);
  const registeringRef = useRef(false);
  const [registerProgress, setRegisterProgress] = useState(0);
  const registerSamplesRef = useRef<Array<[number, number, number]>>([]);
  const lastSampleTimeRef = useRef(0);
  const lastFaceSeen = useRef(0);
  const lastRecognitionSent = useRef(0);
  const knownFaceRef = useRef<KnownFace | null>(loadKnownFace());

  useEffect(() => {
    const handleRegister = (e: any) => {
      if (registeringRef.current) return;
      const prompt = e.detail?.prompt || 'Please hold still while I scan your features.';
      registerSamplesRef.current = [];
      setRegisterProgress(0);
      setRegistering(true);
      registeringRef.current = true;
      setFaceRecognitionStatus('Registering face...');
      sendVisionEvent('face_register_started', { total: REGISTRATION_SAMPLES, prompt });
    };

    const handleIdentify = (e: any) => {
      const prompt = e.detail?.prompt || 'Identifying... One moment, sir.';
      setFaceRecognitionStatus('Identifying...');
      // Identification is continuous, but this confirms the trigger
    };

    window.addEventListener('vision:register', handleRegister as EventListener);
    window.addEventListener('vision:identify', handleIdentify as EventListener);
    return () => {
      window.removeEventListener('vision:register', handleRegister as EventListener);
      window.removeEventListener('vision:identify', handleIdentify as EventListener);
    };
  }, []);

  useEffect(() => {
    if (isInitialized.current) {
      console.log('[VisionTracker] Already initialized, skipping');
      return;
    }
    isInitialized.current = true;

    const loadScripts = (): Promise<void> => {
      return new Promise((resolve) => {
        if (window.Hands && window.Camera && window.FaceMesh) {
          resolve();
          return;
        }

        const existingHands = document.querySelector('script[src*="@mediapipe/hands/hands.js"]');
        const existingCamera = document.querySelector('script[src*="@mediapipe/camera_utils"]');
        const existingFaceMesh = document.querySelector('script[src*="@mediapipe/face_mesh"]');

        if (existingHands && existingCamera && existingFaceMesh) {
          const poll = setInterval(() => {
            if (window.Hands && window.Camera && window.FaceMesh) {
              clearInterval(poll);
              resolve();
            }
          }, 100);
          return;
        }

        const scriptHands = document.createElement('script');
        scriptHands.src = 'https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js';
        scriptHands.crossOrigin = 'anonymous';
        scriptHands.onload = () => {
          const scriptCamera = document.createElement('script');
          scriptCamera.src = 'https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js';
          scriptCamera.crossOrigin = 'anonymous';
          scriptCamera.onload = () => {
            const scriptFaceMesh = document.createElement('script');
            scriptFaceMesh.src = 'https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/face_mesh.js';
            scriptFaceMesh.crossOrigin = 'anonymous';
            scriptFaceMesh.onload = () => resolve();
            scriptFaceMesh.onerror = () => resolve();
            document.body.appendChild(scriptFaceMesh);
          };
          scriptCamera.onerror = () => resolve();
          document.body.appendChild(scriptCamera);
        };
        scriptHands.onerror = () => resolve();
        document.body.appendChild(scriptHands);
      });
    };

    const initVision = async () => {
      await loadScripts();
      if (!videoRef.current) return;
      if (!window.Hands || !window.Camera || !window.FaceMesh) {
        console.error('[VisionTracker] MediaPipe scripts failed to load');
        return;
      }

      try {
        const hands = new window.Hands({
          locateFile: (file: string) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`,
        });

        hands.setOptions({
          maxNumHands: 1,
          modelComplexity: 1,
          minDetectionConfidence: 0.5,
          minTrackingConfidence: 0.5,
        });

        hands.onResults((results: HandResults) => {
          if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
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
                  if (now - lastWave.current > 5000) {
                    lastWave.current = Date.now();
                    console.log('[VisionTracker] WAVE FIRED');
                    onWave();
                  }
                }, 500);
              }
            }
          }
        });

        handsRef.current = hands;

        const faceMesh = new window.FaceMesh({
          locateFile: (file: string) => `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${file}`,
        });

        faceMesh.setOptions({
          maxNumFaces: 1,
          refineLandmarks: true,
          minDetectionConfidence: 0.5,
          minTrackingConfidence: 0.5,
        });

        faceMesh.onResults((results: FaceMeshResults) => {
          const now = Date.now();
          const hasFace = results.multiFaceLandmarks && results.multiFaceLandmarks.length > 0;

          if (hasFace) {
            const landmarks = results.multiFaceLandmarks![0];
            
            // 1. Arrival/Detection logic
            if (!faceDetectedRef.current) {
              const timeAwayMs = now - (lastFaceSeen.current || now);
              const timeAwaySec = timeAwayMs / 1000;
              console.log(`[VisionTracker] Face detected! (Away for ${timeAwaySec.toFixed(1)}s)`);
              sendVisionEvent('face_detected', { new_arrival: timeAwayMs > ABSENCE_TIMEOUT, time_away: timeAwaySec });
              faceDetectedRef.current = true;
              setFaceDetected(true);
            }
            lastFaceSeen.current = now;

            // 2. Registration logic
            if (registeringRef.current && now - lastSampleTimeRef.current > 400) {
              lastSampleTimeRef.current = now;
              const currentSamples = registerSamplesRef.current.length + 1;
              setRegisterProgress(currentSamples);
              
              // Send sample to backend for registration
              sendVisionEvent('face_register_sample', { 
                person_id: 'RED', 
                name: 'RED', 
                landmarks: landmarks,
                sample_index: currentSamples,
                total_samples: REGISTRATION_SAMPLES
              });

              // Mock local progress tracking
              registerSamplesRef.current.push([0,0,0]); // Dummy just to track count
              
              if (currentSamples >= REGISTRATION_SAMPLES) {
                setRegistering(false);
                registeringRef.current = false;
                setFaceRecognitionStatus('Registration Processing...');
              }
              return; // Skip identification while registering
            }

            // 3. Identification logic
            const shouldSendRecognition = now - lastRecognitionSent.current > 1200;
            if (shouldSendRecognition) {
              lastRecognitionSent.current = now;
              // Send landmarks to backend for identification
              sendVisionEvent('face_identify', { landmarks });
            }

          } else {
            if (faceDetectedRef.current && now - lastFaceSeen.current > 5000) {
              console.log('[VisionTracker] Person left the camera area');
              faceDetectedRef.current = false;
              setFaceDetected(false);
              sendVisionEvent('face_lost', { duration: (now - lastFaceSeen.current) / 1000 });
            }
            if (registering) {
              setFaceRecognitionStatus('Waiting for face to register...');
            }
          }
        });

        faceMeshRef.current = faceMesh;

        const camera = new window.Camera(videoRef.current, {
          onFrame: async () => {
            if (!videoRef.current) return;
            try {
              if (handsRef.current) await handsRef.current.send({ image: videoRef.current });
              if (faceMeshRef.current) await faceMeshRef.current.send({ image: videoRef.current });
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
      if (faceMeshRef.current) {
        try { faceMeshRef.current.close(); } catch (e) {}
      }
    };
  }, [onWave]);

  return (
    <div style={{
      position: 'fixed',
      top: 20,
      right: 20,
      zIndex: 10000,
      pointerEvents: 'none',
      display: 'flex',
      flexDirection: 'column',
      gap: '8px',
      alignItems: 'flex-end',
    }}>
      <video
        ref={videoRef}
        style={{ width: '1px', height: '1px', opacity: 0, position: 'absolute' }}
        autoPlay muted playsInline
      />
      <div style={{
        fontSize: '10px',
        color: faceDetected ? '#00ffaa' : 'rgba(255,255,255,0.3)',
        fontFamily: "'Share Tech Mono', monospace",
        letterSpacing: '0.2em',
        textAlign: 'right',
        background: 'rgba(3, 5, 8, 0.7)',
        padding: '8px 16px',
        borderRadius: '2px',
        borderRight: `3px solid ${faceDetected ? '#00ffaa' : 'rgba(255,255,255,0.1)'}`,
        backdropFilter: 'blur(15px)',
        boxShadow: faceDetected ? '0 0 20px rgba(0,255,170,0.3)' : 'none',
        transition: 'all 0.3s ease',
        textTransform: 'uppercase',
        position: 'relative',
        overflow: 'hidden'
      }}>
        {/* Scanning Line Animation */}
        {!faceDetected && (
          <div style={{
            position: 'absolute', top: 0, left: 0, width: '100%', height: '2px',
            background: 'linear-gradient(90deg, transparent, #00ffaa, transparent)',
            animation: 'scanline-hud 2s linear infinite',
            opacity: 0.5
          }} />
        )}
        <span style={{ marginRight: '8px', opacity: 0.5 }}>{faceDetected ? '●' : '○'}</span>
        {faceDetected ? 'Optic Match Active' : 'Scanning for Profile'}
      </div>
      <div style={{
        fontSize: '10px',
        color: faceRecognitionStatus.startsWith('Recognized') ? '#00ff96' : '#ff7788',
        fontFamily: "'Share Tech Mono', monospace",
        letterSpacing: '0.1em',
        textAlign: 'right',
        background: 'rgba(3, 5, 8, 0.6)',
        padding: '6px 12px',
        borderRadius: '2px',
        borderRight: `2px solid ${faceRecognitionStatus.startsWith('Recognized') ? '#00ff96' : '#ff7788'}`,
        backdropFilter: 'blur(10px)',
        transition: 'all 0.3s ease',
        textTransform: 'uppercase'
      }}>
        {faceRecognitionStatus}
        {faceConfidence !== null && faceDetected && (
          <div style={{ fontSize: '9px', color: 'rgba(255,255,255,0.5)', marginTop: '2px' }}>
            Probability {Math.round(faceConfidence * 100)}%
          </div>
        )}
      </div>
      {registering && (
        <div style={{
          fontSize: '10px',
          color: '#a8fff8',
          fontFamily: "'Share Tech Mono', monospace",
          letterSpacing: '0.1em',
          textAlign: 'right',
          background: 'rgba(0, 40, 60, 0.6)',
          padding: '6px 12px',
          borderRadius: '2px',
          borderRight: '2px solid #a8fff8',
          backdropFilter: 'blur(10px)',
          animation: 'pulse 1.5s infinite'
        }}>
          Bio-Auth Capture: {registerProgress}/{REGISTRATION_SAMPLES}
        </div>
      )}
    </div>
  );
};

export default VisionTracker;
