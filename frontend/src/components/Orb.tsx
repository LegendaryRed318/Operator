import React, { useRef, useEffect, useCallback, useState } from 'react';
import * as THREE from 'three';
import { useVoice } from '../contexts/VoiceContext';

interface OrbProps {
  onClick?: () => void;
}

const Orb: React.FC<OrbProps> = ({ onClick }) => {
  const { state, manualWake, audioLevel } = useVoice();
  const mountRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const particlesRef = useRef<THREE.Points | null>(null);
  const glowParticlesRef = useRef<THREE.Points | null>(null);
  const trailsRef = useRef<THREE.LineSegments | null>(null);
  const pulseRef = useRef<THREE.Mesh | null>(null);
  const frameIdRef = useRef<number>(0);
  const timeRef = useRef(0);
  const audioLevelRef = useRef(0); // For smooth interpolation

  const getColor = useCallback(() => {
    switch(state) {
      case 'listening': return new THREE.Color(0x00aaff); // blue
      case 'thinking': return new THREE.Color(0xffaa00);  // orange
      case 'speaking': return new THREE.Color(0x00ffaa);  // teal
      case 'offline': return new THREE.Color(0x666666);   // gray when offline
      default: return new THREE.Color(0x88aaff);          // idle pale blue
    }
  }, [state]);

  useEffect(() => {
    if (!mountRef.current) return;

    // Setup scene with transparent background
    const scene = new THREE.Scene();
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(75, 1, 0.1, 1000);
    camera.position.z = 3;
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(300, 300);
    renderer.setClearColor(0x000000, 0);
    mountRef.current.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Core particle system
    const particleCount = 2000;
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const velocities: THREE.Vector3[] = [];
    
    for (let i = 0; i < particleCount; i++) {
      const radius = 1.0;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const x = radius * Math.sin(phi) * Math.cos(theta);
      const y = radius * Math.sin(phi) * Math.sin(theta);
      const z = radius * Math.cos(phi);
      positions[i*3] = x;
      positions[i*3+1] = y;
      positions[i*3+2] = z;
      velocities.push(new THREE.Vector3(
        (Math.random() - 0.5) * 0.02,
        (Math.random() - 0.5) * 0.02,
        (Math.random() - 0.5) * 0.02
      ));
    }
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const material = new THREE.PointsMaterial({
      color: getColor(),
      size: 0.04,
      transparent: true,
      opacity: 0.9,
      blending: THREE.AdditiveBlending
    });
    const particles = new THREE.Points(geometry, material);
    scene.add(particles);
    particlesRef.current = particles;
    (particles as any).velocities = velocities;

    // Outer glow particles
    const glowGeometry = new THREE.BufferGeometry();
    const glowPositions = new Float32Array(particleCount * 3);
    for (let i = 0; i < particleCount; i++) {
      const radius = 1.4;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      glowPositions[i*3] = radius * Math.sin(phi) * Math.cos(theta);
      glowPositions[i*3+1] = radius * Math.sin(phi) * Math.sin(theta);
      glowPositions[i*3+2] = radius * Math.cos(phi);
    }
    glowGeometry.setAttribute('position', new THREE.BufferAttribute(glowPositions, 3));
    const glowMaterial = new THREE.PointsMaterial({ 
      color: getColor(), 
      size: 0.015, 
      transparent: true, 
      opacity: 0.4, 
      blending: THREE.AdditiveBlending 
    });
    const glowParticles = new THREE.Points(glowGeometry, glowMaterial);
    scene.add(glowParticles);
    glowParticlesRef.current = glowParticles;

    // Electron trails (for thinking state)
    const trailCount = 20;
    const trailGeometry = new THREE.BufferGeometry();
    const trailPositions = new Float32Array(trailCount * 6); // 2 points per line
    trailGeometry.setAttribute('position', new THREE.BufferAttribute(trailPositions, 3));
    const trailMaterial = new THREE.LineBasicMaterial({
      color: 0xffaa00,
      transparent: true,
      opacity: 0,
      blending: THREE.AdditiveBlending
    });
    const trails = new THREE.LineSegments(trailGeometry, trailMaterial);
    scene.add(trails);
    trailsRef.current = trails;
    (trails as any).trailData = Array(trailCount).fill(null).map(() => ({
      angle: Math.random() * Math.PI * 2,
      radius: 1.2 + Math.random() * 0.5,
      speed: 0.02 + Math.random() * 0.03,
      yOffset: (Math.random() - 0.5) * 2
    }));

    // Pulse ring (for listening state)
    const pulseGeometry = new THREE.RingGeometry(1.3, 1.5, 64);
    const pulseMaterial = new THREE.MeshBasicMaterial({
      color: 0x00aaff,
      transparent: true,
      opacity: 0,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending
    });
    const pulse = new THREE.Mesh(pulseGeometry, pulseMaterial);
    pulse.lookAt(camera.position);
    scene.add(pulse);
    pulseRef.current = pulse;

    // Animation loop
    const animate = () => {
      frameIdRef.current = requestAnimationFrame(animate);
      timeRef.current += 0.016;
      const time = timeRef.current;

      // Smooth audio level interpolation
      audioLevelRef.current += (audioLevel - audioLevelRef.current) * 0.2;
      const audioPulse = audioLevelRef.current;

      // Core rotation - speeds up with audio
      const rotationSpeed = 0.003 + audioPulse * 0.01;
      particles.rotation.y += rotationSpeed;
      particles.rotation.x += 0.002 + audioPulse * 0.005;
      glowParticles.rotation.y -= 0.001 + audioPulse * 0.003;
      glowParticles.rotation.x -= 0.0005;

      // State-based animations
      if (state === 'listening' && pulseRef.current) {
        // Audio-reactive pulse effect
        const basePulse = Math.sin(time * 4) * 0.15;
        const audioScale = 1 + basePulse + audioPulse * 0.5;
        pulseRef.current.scale.set(audioScale, audioScale, 1);
        (pulseRef.current.material as THREE.MeshBasicMaterial).opacity =
          0.3 + Math.sin(time * 4) * 0.2 + audioPulse * 0.5;
        pulseRef.current.rotation.z += 0.01 + audioPulse * 0.05;
      } else if (pulseRef.current) {
        (pulseRef.current.material as THREE.MeshBasicMaterial).opacity = 0;
      }

      if (state === 'thinking' && trailsRef.current) {
        // Electron trails animation
        const trailData = (trailsRef.current as any).trailData;
        const positions = trailsRef.current.geometry.attributes.position.array as Float32Array;
        
        for (let i = 0; i < trailCount; i++) {
          const data = trailData[i];
          data.angle += data.speed;
          
          const x1 = Math.cos(data.angle) * data.radius;
          const z1 = Math.sin(data.angle) * data.radius;
          const y1 = data.yOffset + Math.sin(time * 2 + i) * 0.3;
          
          const x2 = Math.cos(data.angle + 0.1) * (data.radius + 0.1);
          const z2 = Math.sin(data.angle + 0.1) * (data.radius + 0.1);
          const y2 = y1 + 0.05;
          
          positions[i*6] = x1;
          positions[i*6+1] = y1;
          positions[i*6+2] = z1;
          positions[i*6+3] = x2;
          positions[i*6+4] = y2;
          positions[i*6+5] = z2;
        }
        
        trailsRef.current.geometry.attributes.position.needsUpdate = true;
        (trailsRef.current.material as THREE.LineBasicMaterial).opacity = 
          0.6 + Math.sin(time * 3) * 0.2;
      } else if (trailsRef.current) {
        (trailsRef.current.material as THREE.LineBasicMaterial).opacity = 0;
      }

      // Particle breathing effect - audio reactive
      if (particlesRef.current) {
        const positions = particlesRef.current.geometry.attributes.position.array as Float32Array;
        const velocities = (particlesRef.current as any).velocities;
        const color = getColor();

        // Expand particle size with audio
        (particlesRef.current.material as THREE.PointsMaterial).size = 0.04 + audioPulse * 0.08;

        for (let i = 0; i < particleCount; i++) {
          const idx = i * 3;
          const v = velocities[i];

          // Apply velocity with breathing - audio reactive intensity
          const audioIntensity = 1 + audioPulse * 3;
          positions[idx] += (v.x + Math.sin(time + i * 0.1) * 0.001) * audioIntensity;
          positions[idx+1] += (v.y + Math.cos(time + i * 0.1) * 0.001) * audioIntensity;
          positions[idx+2] += v.z * audioIntensity;

          // Keep within bounds - expand bounds with audio
          const maxDist = 1.5 + audioPulse * 0.5;
          const dist = Math.sqrt(positions[idx]**2 + positions[idx+1]**2 + positions[idx+2]**2);
          if (dist > maxDist) {
            positions[idx] *= 0.95;
            positions[idx+1] *= 0.95;
            positions[idx+2] *= 0.95;
          }
        }
        particlesRef.current.geometry.attributes.position.needsUpdate = true;
        (particlesRef.current.material as THREE.PointsMaterial).color.lerp(color, 0.05);
      }

      if (glowParticlesRef.current) {
        (glowParticlesRef.current.material as THREE.PointsMaterial).color.lerp(getColor(), 0.03);
      }

      renderer.render(scene, camera);
    };
    animate();

    return () => {
      cancelAnimationFrame(frameIdRef.current);
      if (rendererRef.current && mountRef.current) {
        mountRef.current.removeChild(rendererRef.current.domElement);
      }
      geometry.dispose();
      material.dispose();
      glowGeometry.dispose();
      glowMaterial.dispose();
      trailGeometry.dispose();
      trailMaterial.dispose();
      pulseGeometry.dispose();
      pulseMaterial.dispose();
      renderer.dispose();
    };
  }, [state, getColor, audioLevel]);

  const [showHint, setShowHint] = useState(false);

  // Push-to-talk keyboard support
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === 'Space' && !e.repeat && state === 'idle') {
        e.preventDefault();
        manualWake();
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code === 'Space' && state === 'listening') {
        // Space released - could trigger end of speech here if needed
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);

    // Show hint after 3 seconds
    const hintTimer = setTimeout(() => setShowHint(true), 3000);
    const hideHintTimer = setTimeout(() => setShowHint(false), 8000);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      clearTimeout(hintTimer);
      clearTimeout(hideHintTimer);
    };
  }, [state, manualWake]);

  const handleClick = () => {
    // Call optional external onClick handler
    onClick?.();
    // Trigger voice wake
    manualWake();
  };

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      <div
        ref={mountRef}
        onClick={handleClick}
        style={{
          width: '300px',
          height: '300px',
          margin: '0 auto',
          cursor: 'pointer',
          borderRadius: '50%',
          filter: state === 'speaking' ? 'drop-shadow(0 0 20px #00ffaa)' :
                  state === 'offline' ? 'drop-shadow(0 0 10px #666666)' : 'none',
          transition: 'filter 0.3s ease'
        }}
      />
      {/* Push-to-talk hint */}
      {showHint && state === 'idle' && (
        <div style={{
          position: 'absolute',
          bottom: '-30px',
          left: '50%',
          transform: 'translateX(-50%)',
          fontSize: '11px',
          color: 'rgba(0, 180, 255, 0.7)',
          fontFamily: "'Share Tech Mono', monospace",
          letterSpacing: '0.1em',
          pointerEvents: 'none',
          animation: 'fadeInOut 5s ease-in-out'
        }}>
          CLICK OR HOLD SPACE
        </div>
      )}
    </div>
  );
};

export default Orb;
