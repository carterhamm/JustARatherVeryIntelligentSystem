import { useRef, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { glowVertexShader, glowFragmentShader, coreVertexShader, coreFragmentShader } from './shaders';

interface GlowingCoreProps {
  isListening: boolean;
  isSpeaking: boolean;
  isThinking: boolean;
  activity: number;
}

export default function GlowingCore({ isListening, isSpeaking, isThinking, activity }: GlowingCoreProps) {
  const innerRef = useRef<THREE.Mesh>(null);
  const outerRef = useRef<THREE.Mesh>(null);
  const coreUniformsRef = useRef({
    uColor: { value: new THREE.Color('#00d4ff') },
    uTime: { value: 0 },
    uActivity: { value: 0 },
  });
  const glowUniformsRef = useRef({
    uColor: { value: new THREE.Color('#00d4ff') },
    uPower: { value: 3.0 },
    uIntensity: { value: 0.8 },
    uTime: { value: 0 },
  });

  const targetColor = useMemo(() => {
    if (isSpeaking) return new THREE.Color('#f0a500');
    if (isThinking) return new THREE.Color('#4080ff');
    if (isListening) return new THREE.Color('#00ff80');
    return new THREE.Color('#00d4ff');
  }, [isListening, isSpeaking, isThinking]);

  useFrame((state) => {
    const time = state.clock.elapsedTime;

    // Update uniforms
    coreUniformsRef.current.uTime.value = time;
    coreUniformsRef.current.uActivity.value = activity;
    glowUniformsRef.current.uTime.value = time;

    // Smooth color transition
    coreUniformsRef.current.uColor.value.lerp(targetColor, 0.05);
    glowUniformsRef.current.uColor.value.lerp(targetColor, 0.05);

    // Pulsing scale
    if (innerRef.current) {
      const baseScale = 1.0;
      const pulse = Math.sin(time * 2) * 0.03 * (1 + activity * 2);
      const breathe = Math.sin(time * 0.5) * 0.02;
      const scale = baseScale + pulse + breathe + activity * 0.1;
      innerRef.current.scale.setScalar(scale);
      innerRef.current.rotation.y = time * 0.1;
    }

    // Outer glow pulses differently
    if (outerRef.current) {
      const outerScale = 1.15 + Math.sin(time * 1.5) * 0.05 + activity * 0.15;
      outerRef.current.scale.setScalar(outerScale);
      outerRef.current.rotation.y = -time * 0.05;
    }
  });

  return (
    <group>
      {/* Inner core sphere */}
      <mesh ref={innerRef}>
        <icosahedronGeometry args={[0.8, 4]} />
        <shaderMaterial
          vertexShader={coreVertexShader}
          fragmentShader={coreFragmentShader}
          uniforms={coreUniformsRef.current}
          transparent
        />
      </mesh>

      {/* Outer glow sphere */}
      <mesh ref={outerRef}>
        <sphereGeometry args={[1.0, 32, 32]} />
        <shaderMaterial
          vertexShader={glowVertexShader}
          fragmentShader={glowFragmentShader}
          uniforms={glowUniformsRef.current}
          transparent
          blending={THREE.AdditiveBlending}
          side={THREE.BackSide}
          depthWrite={false}
        />
      </mesh>

      {/* Point light for illumination */}
      <pointLight
        color={targetColor}
        intensity={1.5 + activity * 2}
        distance={10}
        decay={2}
      />
    </group>
  );
}
