import { useEffect, useState } from 'react';
import { useUIStore } from '@/stores/uiStore';
import { useSettingsStore, type ModelProvider } from '@/stores/settingsStore';

const providerLabels: Record<ModelProvider, string> = {
  openai: 'GPT-4o',
  claude: 'Claude',
  glm: 'GLM-4',
  gemini: 'Gemini',
  stark_protocol: 'Stark',
};

function TinyProgressBar({ value, color = 'rgba(0,212,255,0.4)' }: { value: number; color?: string }) {
  return (
    <div className="w-full h-[2px] bg-white/[0.03] rounded-full overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-1000"
        style={{ width: `${value}%`, background: color }}
      />
    </div>
  );
}

export default function MiniDiagnostics() {
  const activity = useUIStore((s) => s.jarvisActivity);
  const isThinking = useUIStore((s) => s.isThinking);
  const isSpeaking = useUIStore((s) => s.isSpeaking);
  const wsConnected = useUIStore((s) => s.wsConnected);
  const modelPreference = useSettingsStore((s) => s.modelPreference);
  const voiceEnabled = useSettingsStore((s) => s.voiceEnabled);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 2500);
    return () => clearInterval(id);
  }, []);

  const cpu = 25 + activity * 60 + Math.sin(tick * 0.4) * 8;
  const mem = 38 + activity * 25 + Math.sin(tick * 0.6) * 5;
  const gpu = isThinking ? 75 + Math.sin(tick * 0.3) * 15 : 12 + Math.sin(tick * 0.2) * 8;

  return (
    <div className="fixed right-4 top-1/2 -translate-y-1/2 z-10 pointer-events-none boot-5 hidden xl:block">
      <div className="flex flex-col items-end gap-4 w-20">
        {/* Model indicator */}
        <div className="flex flex-col items-end gap-0.5">
          <span className="text-[6px] font-mono tracking-[0.2em] text-jarvis-blue/25 uppercase">
            MODEL
          </span>
          <span className="text-[9px] font-mono text-jarvis-blue/40">
            {providerLabels[modelPreference]}
          </span>
        </div>

        {/* CPU */}
        <div className="w-full flex flex-col items-end gap-0.5">
          <div className="flex items-center justify-between w-full">
            <span className="text-[6px] font-mono tracking-wider text-jarvis-blue/20">CPU</span>
            <span className="text-[8px] font-mono text-jarvis-blue/35 tabular-nums">
              {cpu.toFixed(0)}%
            </span>
          </div>
          <TinyProgressBar value={cpu} />
        </div>

        {/* MEM */}
        <div className="w-full flex flex-col items-end gap-0.5">
          <div className="flex items-center justify-between w-full">
            <span className="text-[6px] font-mono tracking-wider text-jarvis-cyan/20">MEM</span>
            <span className="text-[8px] font-mono text-jarvis-cyan/35 tabular-nums">
              {mem.toFixed(0)}%
            </span>
          </div>
          <TinyProgressBar value={mem} color="rgba(0,240,255,0.35)" />
        </div>

        {/* GPU */}
        <div className="w-full flex flex-col items-end gap-0.5">
          <div className="flex items-center justify-between w-full">
            <span className="text-[6px] font-mono tracking-wider text-jarvis-gold/20">GPU</span>
            <span className="text-[8px] font-mono text-jarvis-gold/35 tabular-nums">
              {gpu.toFixed(0)}%
            </span>
          </div>
          <TinyProgressBar value={gpu} color="rgba(240,165,0,0.35)" />
        </div>

        {/* Divider */}
        <div className="w-8 h-px bg-jarvis-blue/5 self-end" />

        {/* Status dots */}
        <div className="flex flex-col items-end gap-1.5">
          <div className="flex items-center gap-1.5">
            <span className="text-[6px] font-mono text-gray-700 tracking-wider">WS</span>
            <div
              className="w-1 h-1 rounded-full"
              style={{
                background: wsConnected ? '#39ff14' : '#555',
                boxShadow: wsConnected ? '0 0 4px rgba(57,255,20,0.5)' : 'none',
              }}
            />
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[6px] font-mono text-gray-700 tracking-wider">VOX</span>
            <div
              className="w-1 h-1 rounded-full"
              style={{
                background: voiceEnabled ? '#f0a500' : '#555',
                boxShadow: voiceEnabled ? '0 0 4px rgba(240,165,0,0.5)' : 'none',
              }}
            />
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[6px] font-mono text-gray-700 tracking-wider">TTS</span>
            <div
              className="w-1 h-1 rounded-full"
              style={{
                background: isSpeaking ? '#ffbf00' : '#555',
                boxShadow: isSpeaking ? '0 0 4px rgba(255,191,0,0.5)' : 'none',
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
