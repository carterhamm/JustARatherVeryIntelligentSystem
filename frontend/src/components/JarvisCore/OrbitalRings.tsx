import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

interface OrbitalRingsProps {
  activity: number;
}

interface RingConfig {
  radius: number;
  tube: number;
  tiltX: number;
  tiltZ: number;
  speed: number;
  color: string;
  orbiterCount: number;
}

const ringConfigs: RingConfig[] = [
  { radius: 1.6, tube: 0.008, tiltX: 0.3, tiltZ: 0.1, speed: 0.5, color: '#00d4ff', orbiterCount: 3 },
  { radius: 2.2, tube: 0.006, tiltX: -0.5, tiltZ: 0.8, speed: -0.35, color: '#0090ff', orbiterCount: 2 },
  { radius: 2.8, tube: 0.005, tiltX: 0.7, tiltZ: -0.4, speed: 0.25, color: '#00b8ff', orbiterCount: 4 },
];

function OrbitalRing({ config, activity }: { config: RingConfig; activity: number }) {
  const groupRef = useRef<THREE.Group>(null);
  const orbiterRefs = useRef<(THREE.Mesh | null)[]>([]);

  useFrame((state) => {
    const time = state.clock.elapsedTime;
    const speed = config.speed * (1 + activity * 2);

    if (groupRef.current) {
      groupRef.current.rotation.y = time * speed * 0.3;
    }

    // Animate orbiters along the ring
    for (let i = 0; i < config.orbiterCount; i++) {
      const mesh = orbiterRefs.current[i];
      if (mesh) {
        const angle = time * speed + (i * Math.PI * 2) / config.orbiterCount;
        mesh.position.x = Math.cos(angle) * config.radius;
        mesh.position.z = Math.sin(angle) * config.radius;
        mesh.position.y = 0;

        // Pulsing size
        const pulse = 1 + Math.sin(time * 3 + i) * 0.3;
        const baseSize = 0.02 + activity * 0.02;
        mesh.scale.setScalar(baseSize * pulse);
      }
    }
  });

  return (
    <group ref={groupRef} rotation={[config.tiltX, 0, config.tiltZ]}>
      {/* Ring torus */}
      <mesh>
        <torusGeometry args={[config.radius, config.tube, 16, 100]} />
        <meshBasicMaterial
          color={config.color}
          transparent
          opacity={0.3 + activity * 0.3}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>

      {/* Orbiters */}
      {Array.from({ length: config.orbiterCount }).map((_, i) => (
        <mesh
          key={i}
          ref={(el) => {
            orbiterRefs.current[i] = el;
          }}
        >
          <sphereGeometry args={[1, 8, 8]} />
          <meshBasicMaterial
            color={config.color}
            transparent
            opacity={0.8}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
      ))}
    </group>
  );
}

export default function OrbitalRings({ activity }: OrbitalRingsProps) {
  return (
    <group>
      {ringConfigs.map((config, index) => (
        <OrbitalRing key={index} config={config} activity={activity} />
      ))}
    </group>
  );
}
