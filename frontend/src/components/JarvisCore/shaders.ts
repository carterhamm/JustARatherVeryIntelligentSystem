export const particleVertexShader = `
  uniform float uTime;
  uniform float uActivity;

  attribute float aSize;
  attribute float aOpacity;
  attribute float aSpeed;

  varying float vOpacity;
  varying float vDistance;

  void main() {
    vec3 pos = position;

    float speed = aSpeed * (1.0 + uActivity * 2.0);

    // Orbital motion
    float angle = uTime * speed * 0.1;
    float cosA = cos(angle);
    float sinA = sin(angle);
    pos.xz = mat2(cosA, -sinA, sinA, cosA) * pos.xz;

    // Subtle vertical oscillation
    pos.y += sin(uTime * speed * 0.3 + pos.x * 2.0) * 0.15;

    // Pull toward center when active
    float pullStrength = uActivity * 0.3;
    vec3 toCenter = -normalize(pos) * pullStrength;
    pos += toCenter;

    // Breathing effect
    float breathe = 1.0 + sin(uTime * 0.5) * 0.05;
    pos *= breathe;

    vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);

    vDistance = length(mvPosition.xyz);
    vOpacity = aOpacity * (1.0 - smoothstep(3.0, 12.0, vDistance));

    // Size attenuation
    float size = aSize * (1.0 + uActivity * 0.5);
    gl_PointSize = size * (200.0 / -mvPosition.z);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

export const particleFragmentShader = `
  uniform vec3 uColor;
  uniform float uActivity;

  varying float vOpacity;
  varying float vDistance;

  void main() {
    // Circular soft particle
    vec2 center = gl_PointCoord - 0.5;
    float dist = length(center);

    if (dist > 0.5) discard;

    // Soft radial gradient
    float alpha = 1.0 - smoothstep(0.0, 0.5, dist);
    alpha *= alpha; // Quadratic falloff for softer look

    // Glow effect
    float glow = exp(-dist * 4.0) * 0.5;

    vec3 color = uColor + glow * vec3(0.2, 0.4, 0.6);
    float finalAlpha = (alpha + glow) * vOpacity;

    gl_FragColor = vec4(color, finalAlpha);
  }
`;

export const glowVertexShader = `
  varying vec3 vNormal;
  varying vec3 vViewPosition;

  void main() {
    vNormal = normalize(normalMatrix * normal);
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    vViewPosition = -mvPosition.xyz;
    gl_Position = projectionMatrix * mvPosition;
  }
`;

export const glowFragmentShader = `
  uniform vec3 uColor;
  uniform float uPower;
  uniform float uIntensity;
  uniform float uTime;

  varying vec3 vNormal;
  varying vec3 vViewPosition;

  void main() {
    vec3 viewDir = normalize(vViewPosition);
    float fresnel = 1.0 - abs(dot(viewDir, vNormal));
    fresnel = pow(fresnel, uPower);

    // Pulsing intensity
    float pulse = 1.0 + sin(uTime * 2.0) * 0.15;

    float alpha = fresnel * uIntensity * pulse;

    // Slight color variation across surface
    vec3 color = uColor;
    color += vec3(0.1, 0.05, 0.0) * sin(vNormal.y * 3.14159 + uTime);

    gl_FragColor = vec4(color, alpha);
  }
`;

export const coreVertexShader = `
  varying vec3 vNormal;
  varying vec2 vUv;
  varying vec3 vPosition;

  void main() {
    vNormal = normalize(normalMatrix * normal);
    vUv = uv;
    vPosition = position;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

export const coreFragmentShader = `
  uniform vec3 uColor;
  uniform float uTime;
  uniform float uActivity;

  varying vec3 vNormal;
  varying vec2 vUv;
  varying vec3 vPosition;

  void main() {
    // Base color with slight surface variation
    vec3 color = uColor;

    // Hex grid pattern
    float scale = 20.0;
    vec2 grid = fract(vUv * scale);
    float pattern = step(0.05, grid.x) * step(0.05, grid.y);

    // Energy lines flowing across surface
    float energy = sin(vPosition.y * 10.0 - uTime * 3.0) * 0.5 + 0.5;
    energy *= sin(vPosition.x * 8.0 + uTime * 2.0) * 0.5 + 0.5;

    color += vec3(0.1, 0.2, 0.3) * energy * uActivity;

    // Emissive glow
    float emissive = 0.3 + uActivity * 0.4;

    gl_FragColor = vec4(color * (pattern * 0.3 + 0.7) * (1.0 + emissive), 1.0);
  }
`;
