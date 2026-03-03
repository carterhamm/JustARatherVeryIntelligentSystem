import { useRef, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

interface HUDOverlay3DProps {
  activity: number;
}

/**
 * Circular targeting reticle ring around the core orb with tick marks.
 */
export default function HUDOverlay3D({ activity }: HUDOverlay3DProps) {
  const groupRef = useRef<THREE.Group>(null);

  // Generate ring geometries
  const { innerLine, outerLine, tickSegments } = useMemo(() => {
    const innerRadius = 2.2;
    const outerRadius = 2.6;
    const segments = 128;
    const tickCount = 36;

    // Inner ring
    const innerPoints: THREE.Vector3[] = [];
    for (let i = 0; i <= segments; i++) {
      const angle = (i / segments) * Math.PI * 2;
      innerPoints.push(new THREE.Vector3(Math.cos(angle) * innerRadius, Math.sin(angle) * innerRadius, 0));
    }
    const innerGeom = new THREE.BufferGeometry().setFromPoints(innerPoints);
    const innerMat = new THREE.LineBasicMaterial({ color: '#00d4ff', transparent: true, opacity: 0.15 });
    const innerLine = new THREE.Line(innerGeom, innerMat);

    // Outer ring
    const outerPoints: THREE.Vector3[] = [];
    for (let i = 0; i <= segments; i++) {
      const angle = (i / segments) * Math.PI * 2;
      outerPoints.push(new THREE.Vector3(Math.cos(angle) * outerRadius, Math.sin(angle) * outerRadius, 0));
    }
    const outerGeom = new THREE.BufferGeometry().setFromPoints(outerPoints);
    const outerMat = new THREE.LineDashedMaterial({
      color: '#00d4ff', transparent: true, opacity: 0.1,
      dashSize: 0.15, gapSize: 0.1,
    });
    const outerLine = new THREE.Line(outerGeom, outerMat);
    outerLine.computeLineDistances();

    // Tick marks
    const tickPoints: THREE.Vector3[] = [];
    for (let i = 0; i < tickCount; i++) {
      const angle = (i / tickCount) * Math.PI * 2;
      const isLong = i % 9 === 0;
      const tickInner = isLong ? innerRadius - 0.15 : innerRadius - 0.08;
      const tickOuter = innerRadius + 0.05;
      tickPoints.push(
        new THREE.Vector3(Math.cos(angle) * tickInner, Math.sin(angle) * tickInner, 0),
        new THREE.Vector3(Math.cos(angle) * tickOuter, Math.sin(angle) * tickOuter, 0),
      );
    }
    const tickGeom = new THREE.BufferGeometry().setFromPoints(tickPoints);
    const tickMat = new THREE.LineBasicMaterial({ color: '#00d4ff', transparent: true, opacity: 0.12 });
    const tickSegments = new THREE.LineSegments(tickGeom, tickMat);

    return { innerLine, outerLine, tickSegments };
  }, []);

  useFrame(({ clock }) => {
    if (groupRef.current) {
      groupRef.current.rotation.z = clock.getElapsedTime() * 0.05 * (1 + activity * 0.5);

      // Update opacity based on activity
      const baseOpacity = 0.15 + activity * 0.2;
      (innerLine.material as THREE.LineBasicMaterial).opacity = baseOpacity;
      (outerLine.material as THREE.LineDashedMaterial).opacity = baseOpacity * 0.6;
      (tickSegments.material as THREE.LineBasicMaterial).opacity = baseOpacity * 0.8;
    }
  });

  return (
    <group ref={groupRef}>
      <primitive object={innerLine} />
      <primitive object={outerLine} />
      <primitive object={tickSegments} />

      {/* Corner bracket indicators */}
      {[0, Math.PI / 2, Math.PI, Math.PI * 1.5].map((angle, i) => (
        <group key={i} rotation={[0, 0, angle]}>
          <mesh position={[2.8, 0, 0]}>
            <planeGeometry args={[0.12, 0.02]} />
            <meshBasicMaterial color="#00d4ff" transparent opacity={0.2 + activity * 0.15} />
          </mesh>
          <mesh position={[2.73, 0.04, 0]}>
            <planeGeometry args={[0.02, 0.1]} />
            <meshBasicMaterial color="#00d4ff" transparent opacity={0.2 + activity * 0.15} />
          </mesh>
        </group>
      ))}
    </group>
  );
}
