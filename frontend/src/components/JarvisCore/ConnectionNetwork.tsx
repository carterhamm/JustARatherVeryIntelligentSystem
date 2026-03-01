import { useRef, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

interface ConnectionNetworkProps {
  activity: number;
  pointCount?: number;
  connectionThreshold?: number;
}

export default function ConnectionNetwork({
  activity,
  pointCount = 50,
  connectionThreshold = 2.5,
}: ConnectionNetworkProps) {
  const lineRef = useRef<THREE.LineSegments>(null);
  const dotsRef = useRef<THREE.Points>(null);

  const { points, dotPositions } = useMemo(() => {
    const points: THREE.Vector3[] = [];
    const dotPositions = new Float32Array(pointCount * 3);

    for (let i = 0; i < pointCount; i++) {
      const radius = 2.0 + Math.random() * 1.5;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);

      const x = radius * Math.sin(phi) * Math.cos(theta);
      const y = radius * Math.sin(phi) * Math.sin(theta);
      const z = radius * Math.cos(phi);

      points.push(new THREE.Vector3(x, y, z));
      dotPositions[i * 3] = x;
      dotPositions[i * 3 + 1] = y;
      dotPositions[i * 3 + 2] = z;
    }

    return { points, dotPositions };
  }, [pointCount]);

  const maxSegments = pointCount * pointCount;
  const linePositions = useMemo(() => new Float32Array(maxSegments * 6), [maxSegments]);
  const lineColors = useMemo(() => new Float32Array(maxSegments * 6), [maxSegments]);

  const lineGeometry = useMemo(() => {
    const geom = new THREE.BufferGeometry();
    geom.setAttribute('position', new THREE.BufferAttribute(linePositions, 3));
    geom.setAttribute('color', new THREE.BufferAttribute(lineColors, 3));
    geom.setDrawRange(0, 0);
    return geom;
  }, [linePositions, lineColors]);

  useFrame((state) => {
    const time = state.clock.elapsedTime;

    // Animate points
    const currentPoints: THREE.Vector3[] = [];
    for (let i = 0; i < pointCount; i++) {
      const p = points[i].clone();
      const offset = i * 0.1;

      p.x += Math.sin(time * 0.3 + offset) * 0.2;
      p.y += Math.cos(time * 0.4 + offset * 1.3) * 0.2;
      p.z += Math.sin(time * 0.2 + offset * 0.7) * 0.2;

      currentPoints.push(p);

      if (dotsRef.current) {
        const posAttr = dotsRef.current.geometry.attributes.position as THREE.BufferAttribute;
        posAttr.setXYZ(i, p.x, p.y, p.z);
      }
    }

    if (dotsRef.current) {
      (dotsRef.current.geometry.attributes.position as THREE.BufferAttribute).needsUpdate = true;
    }

    // Build connections
    let lineIndex = 0;
    const threshold = connectionThreshold + activity * 1.0;
    const color = new THREE.Color('#00d4ff');

    for (let i = 0; i < pointCount; i++) {
      for (let j = i + 1; j < pointCount; j++) {
        const dist = currentPoints[i].distanceTo(currentPoints[j]);
        if (dist < threshold) {
          const alpha = 1 - dist / threshold;
          const fade = (Math.sin(time + i * 0.5 + j * 0.3) * 0.5 + 0.5) * alpha;

          const idx = lineIndex * 6;
          linePositions[idx] = currentPoints[i].x;
          linePositions[idx + 1] = currentPoints[i].y;
          linePositions[idx + 2] = currentPoints[i].z;
          linePositions[idx + 3] = currentPoints[j].x;
          linePositions[idx + 4] = currentPoints[j].y;
          linePositions[idx + 5] = currentPoints[j].z;

          lineColors[idx] = color.r * fade;
          lineColors[idx + 1] = color.g * fade;
          lineColors[idx + 2] = color.b * fade;
          lineColors[idx + 3] = color.r * fade;
          lineColors[idx + 4] = color.g * fade;
          lineColors[idx + 5] = color.b * fade;

          lineIndex++;
        }
      }
    }

    if (lineRef.current) {
      const posAttr = lineRef.current.geometry.attributes.position as THREE.BufferAttribute;
      const colAttr = lineRef.current.geometry.attributes.color as THREE.BufferAttribute;
      posAttr.needsUpdate = true;
      colAttr.needsUpdate = true;
      lineRef.current.geometry.setDrawRange(0, lineIndex * 2);
    }
  });

  return (
    <group>
      {/* Connection lines */}
      <lineSegments ref={lineRef} geometry={lineGeometry}>
        <lineBasicMaterial
          vertexColors
          transparent
          opacity={0.4 + activity * 0.3}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </lineSegments>

      {/* Node dots */}
      <points ref={dotsRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            array={dotPositions}
            count={pointCount}
            itemSize={3}
          />
        </bufferGeometry>
        <pointsMaterial
          color="#00d4ff"
          size={3}
          sizeAttenuation
          transparent
          opacity={0.6 + activity * 0.3}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </points>
    </group>
  );
}
