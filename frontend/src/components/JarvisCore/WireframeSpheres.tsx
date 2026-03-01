import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

interface WireframeSpheresProps {
  activity: number;
}

interface SphereConfig {
  radius: number;
  detail: number;
  opacity: number;
  rotationAxis: THREE.Vector3;
  rotationSpeed: number;
  color: string;
}

const sphereConfigs: SphereConfig[] = [
  {
    radius: 1.2,
    detail: 1,
    opacity: 0.25,
    rotationAxis: new THREE.Vector3(0, 1, 0.3).normalize(),
    rotationSpeed: 0.15,
    color: '#00d4ff',
  },
  {
    radius: 1.8,
    detail: 2,
    opacity: 0.18,
    rotationAxis: new THREE.Vector3(0.5, 1, 0).normalize(),
    rotationSpeed: -0.1,
    color: '#0090ff',
  },
  {
    radius: 2.5,
    detail: 1,
    opacity: 0.12,
    rotationAxis: new THREE.Vector3(-0.3, 1, 0.5).normalize(),
    rotationSpeed: 0.07,
    color: '#00b8ff',
  },
];

function WireframeLayer({ config, activity }: { config: SphereConfig; activity: number }) {
  const meshRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    if (!meshRef.current) return;
    const time = state.clock.elapsedTime;
    const speed = config.rotationSpeed * (1 + activity * 1.5);

    meshRef.current.rotation.x += config.rotationAxis.x * speed * 0.01;
    meshRef.current.rotation.y += config.rotationAxis.y * speed * 0.01;
    meshRef.current.rotation.z += config.rotationAxis.z * speed * 0.01;

    // Subtle breathing
    const breathe = 1 + Math.sin(time * 0.3 + config.radius) * 0.02;
    meshRef.current.scale.setScalar(breathe);
  });

  return (
    <mesh ref={meshRef}>
      <icosahedronGeometry args={[config.radius, config.detail]} />
      <meshBasicMaterial
        color={config.color}
        wireframe
        transparent
        opacity={config.opacity + activity * 0.1}
        blending={THREE.AdditiveBlending}
        depthWrite={false}
      />
    </mesh>
  );
}

export default function WireframeSpheres({ activity }: WireframeSpheresProps) {
  return (
    <group>
      {sphereConfigs.map((config, index) => (
        <WireframeLayer key={index} config={config} activity={activity} />
      ))}
    </group>
  );
}
