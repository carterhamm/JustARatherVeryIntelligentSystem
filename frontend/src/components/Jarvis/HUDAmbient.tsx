import { useEffect, useState, useRef } from 'react';
import { useUIStore } from '@/stores/uiStore';

function CornerBracket({ position }: { position: 'tl' | 'tr' | 'bl' | 'br' }) {
  const isTop = position.startsWith('t');
  const isLeft = position.endsWith('l');

  return (
    <div
      className="absolute pointer-events-none"
      style={{
        [isTop ? 'top' : 'bottom']: '12px',
        [isLeft ? 'left' : 'right']: '12px',
      }}
    >
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
        <path
          d={
            isTop && isLeft
              ? 'M0 12 L0 0 L12 0'
              : isTop && !isLeft
                ? 'M20 0 L32 0 L32 12'
                : !isTop && isLeft
                  ? 'M0 20 L0 32 L12 32'
                  : 'M20 32 L32 32 L32 20'
          }
          stroke="rgba(0, 212, 255, 0.2)"
          strokeWidth="1"
        />
      </svg>
    </div>
  );
}

function DataTicker() {
  const [values, setValues] = useState<number[]>([]);

  useEffect(() => {
    const gen = () =>
      Array.from({ length: 12 }, () => Math.random() * 100);
    setValues(gen());
    const id = setInterval(() => setValues(gen()), 3000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="flex items-end gap-[2px] h-[18px]">
      {values.map((v, i) => (
        <div
          key={i}
          className="w-[2px] rounded-t-sm transition-all duration-700"
          style={{
            height: `${Math.max(15, v)}%`,
            background: `rgba(0, 212, 255, ${0.15 + (v / 100) * 0.35})`,
          }}
        />
      ))}
    </div>
  );
}

function HexReadout({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-center gap-0.5">
      <span className="text-[7px] font-mono tracking-[0.2em] text-jarvis-blue/30 uppercase">
        {label}
      </span>
      <span className="text-[10px] font-mono text-jarvis-blue/50 tabular-nums">
        {value}
      </span>
    </div>
  );
}

function EdgeReadouts() {
  const [tick, setTick] = useState(0);
  const activity = useUIStore((s) => s.jarvisActivity);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 2000);
    return () => clearInterval(id);
  }, []);

  const lat = (12 + Math.sin(tick * 0.3) * 8).toFixed(1);
  const mem = (42 + Math.sin(tick * 0.5) * 15).toFixed(0);
  const net = (0.8 + Math.sin(tick * 0.2) * 0.5).toFixed(2);
  const cores = (activity * 100).toFixed(0);

  return (
    <>
      {/* Bottom left data readout */}
      <div className="fixed bottom-2 left-14 z-10 flex items-center gap-4 pointer-events-none boot-5">
        <HexReadout label="LAT" value={`${lat}ms`} />
        <div className="w-px h-3 bg-jarvis-blue/10" />
        <HexReadout label="MEM" value={`${mem}%`} />
        <div className="w-px h-3 bg-jarvis-blue/10" />
        <HexReadout label="NET" value={`${net}Gb`} />
        <div className="w-px h-3 bg-jarvis-blue/10" />
        <HexReadout label="LOAD" value={`${cores}%`} />
      </div>

      {/* Bottom right data ticker */}
      <div className="fixed bottom-2 right-4 z-10 flex items-center gap-3 pointer-events-none boot-5">
        <DataTicker />
        <span className="text-[7px] font-mono tracking-wider text-jarvis-blue/25">
          SYS.TELEMETRY
        </span>
      </div>

      {/* Top right secondary readout */}
      <div className="fixed top-[72px] right-4 z-10 pointer-events-none boot-5">
        <div className="flex flex-col items-end gap-1">
          <div className="flex items-center gap-2">
            <span className="text-[7px] font-mono text-jarvis-blue/20 tracking-wider">
              NEURAL.PROC
            </span>
            <div className="w-16 h-[2px] bg-jarvis-blue/10 rounded-full overflow-hidden">
              <div
                className="h-full bg-jarvis-blue/30 rounded-full transition-all duration-1000"
                style={{ width: `${30 + activity * 60}%` }}
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[7px] font-mono text-jarvis-blue/20 tracking-wider">
              QUANT.BUFF
            </span>
            <div className="w-16 h-[2px] bg-jarvis-blue/10 rounded-full overflow-hidden">
              <div
                className="h-full bg-jarvis-cyan/30 rounded-full transition-all duration-1000"
                style={{ width: `${50 + Math.sin(tick * 0.7) * 20}%` }}
              />
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function ScanGrid() {
  return (
    <div className="absolute inset-0 pointer-events-none z-[1] overflow-hidden">
      {/* Subtle hex grid pattern */}
      <div
        className="absolute inset-0 opacity-[0.015]"
        style={{
          backgroundImage: `
            linear-gradient(30deg, rgba(0,212,255,0.5) 12%, transparent 12.5%, transparent 87%, rgba(0,212,255,0.5) 87.5%, rgba(0,212,255,0.5)),
            linear-gradient(150deg, rgba(0,212,255,0.5) 12%, transparent 12.5%, transparent 87%, rgba(0,212,255,0.5) 87.5%, rgba(0,212,255,0.5)),
            linear-gradient(30deg, rgba(0,212,255,0.5) 12%, transparent 12.5%, transparent 87%, rgba(0,212,255,0.5) 87.5%, rgba(0,212,255,0.5)),
            linear-gradient(150deg, rgba(0,212,255,0.5) 12%, transparent 12.5%, transparent 87%, rgba(0,212,255,0.5) 87.5%, rgba(0,212,255,0.5)),
            linear-gradient(60deg, rgba(0,212,255,0.3) 25%, transparent 25.5%, transparent 75%, rgba(0,212,255,0.3) 75%, rgba(0,212,255,0.3)),
            linear-gradient(60deg, rgba(0,212,255,0.3) 25%, transparent 25.5%, transparent 75%, rgba(0,212,255,0.3) 75%, rgba(0,212,255,0.3))
          `,
          backgroundSize: '80px 140px',
          backgroundPosition: '0 0, 0 0, 40px 70px, 40px 70px, 0 0, 40px 70px',
        }}
      />
    </div>
  );
}

export default function HUDAmbient() {
  return (
    <>
      <CornerBracket position="tl" />
      <CornerBracket position="tr" />
      <CornerBracket position="bl" />
      <CornerBracket position="br" />
      <ScanGrid />
      <EdgeReadouts />
    </>
  );
}
