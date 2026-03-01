import { useRef, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

interface HolographicGridProps {
  activity: number;
  visible?: boolean;
}

export default function HolographicGrid({ activity, visible = true }: HolographicGridProps) {
  const gridRef = useRef<THREE.Group>(null);

  const gridLines = useMemo(() => {
    const lines: { start: THREE.Vector3; end: THREE.Vector3 }[] = [];
    const size = 20;
    const divisions = 40;
    const step = size / divisions;

    for (let i = -divisions / 2; i <= divisions / 2; i++) {
      const pos = i * step;
      lines.push({
        start: new THREE.Vector3(pos, 0, -size / 2),
        end: new THREE.Vector3(pos, 0, size / 2),
      });
      lines.push({
        start: new THREE.Vector3(-size / 2, 0, pos),
        end: new THREE.Vector3(size / 2, 0, pos),
      });
    }

    return lines;
  }, []);

  const linePositions = useMemo(() => {
    const positions = new Float32Array(gridLines.length * 6);
    gridLines.forEach((line, i) => {
      positions[i * 6] = line.start.x;
      positions[i * 6 + 1] = line.start.y;
      positions[i * 6 + 2] = line.start.z;
      positions[i * 6 + 3] = line.end.x;
      positions[i * 6 + 4] = line.end.y;
      positions[i * 6 + 5] = line.end.z;
    });
    return positions;
  }, [gridLines]);

  useFrame((state) => {
    if (gridRef.current) {
      const time = state.clock.elapsedTime;
      gridRef.current.position.y = -4 + Math.sin(time * 0.2) * 0.1;
    }
  });

  if (!visible) return null;

  return (
    <group ref={gridRef} position={[0, -4, 0]}>
      <lineSegments>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            array={linePositions}
            count={gridLines.length * 2}
            itemSize={3}
          />
        </bufferGeometry>
        <lineBasicMaterial
          color="#00d4ff"
          transparent
          opacity={0.06 + activity * 0.04}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </lineSegments>
    </group>
  );
}
