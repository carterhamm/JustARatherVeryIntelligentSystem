import { useRef, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { particleVertexShader, particleFragmentShader } from './shaders';

interface ParticleSystemProps {
  activity: number;
  count?: number;
}

export default function ParticleSystem({ activity, count = 10000 }: ParticleSystemProps) {
  const pointsRef = useRef<THREE.Points>(null);

  const uniforms = useRef({
    uTime: { value: 0 },
    uActivity: { value: 0 },
    uColor: { value: new THREE.Color('#00d4ff') },
  });

  const { positions, sizes, opacities, speeds } = useMemo(() => {
    const positions = new Float32Array(count * 3);
    const sizes = new Float32Array(count);
    const opacities = new Float32Array(count);
    const speeds = new Float32Array(count);

    for (let i = 0; i < count; i++) {
      // Distribute particles in a spherical shell (radius 3-8)
      const radius = 3 + Math.random() * 5;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);

      positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
      positions[i * 3 + 2] = radius * Math.cos(phi);

      sizes[i] = 1.5 + Math.random() * 3;
      opacities[i] = 0.1 + Math.random() * 0.6;
      speeds[i] = 0.2 + Math.random() * 1.5;
    }

    return { positions, sizes, opacities, speeds };
  }, [count]);

  useFrame((state) => {
    uniforms.current.uTime.value = state.clock.elapsedTime;
    uniforms.current.uActivity.value += (activity - uniforms.current.uActivity.value) * 0.05;
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          array={positions}
          count={count}
          itemSize={3}
        />
        <bufferAttribute
          attach="attributes-aSize"
          array={sizes}
          count={count}
          itemSize={1}
        />
        <bufferAttribute
          attach="attributes-aOpacity"
          array={opacities}
          count={count}
          itemSize={1}
        />
        <bufferAttribute
          attach="attributes-aSpeed"
          array={speeds}
          count={count}
          itemSize={1}
        />
      </bufferGeometry>
      <shaderMaterial
        vertexShader={particleVertexShader}
        fragmentShader={particleFragmentShader}
        uniforms={uniforms.current}
        transparent
        blending={THREE.AdditiveBlending}
        depthWrite={false}
      />
    </points>
  );
}
