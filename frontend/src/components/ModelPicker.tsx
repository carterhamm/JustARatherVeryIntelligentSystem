import { useSettingsStore, ModelProvider } from '@/stores/settingsStore';
import clsx from 'clsx';

interface ModelDef {
  id: ModelProvider;
  label: string;
  description: string;
  activeColor: string;
}

const uplinkModels: ModelDef[] = [
  {
    id: 'openai',
    label: 'OpenAI',
    description: 'GPT-4o — versatile, fast, vision',
    activeColor: 'border-green-400/20 text-green-400',
  },
  {
    id: 'claude',
    label: 'Claude',
    description: 'Sonnet 4 — nuanced reasoning',
    activeColor: 'border-orange-400/20 text-orange-400',
  },
  {
    id: 'glm',
    label: 'GLM-4',
    description: 'ZhipuAI Coding Pro — fast, capable',
    activeColor: 'border-purple-400/20 text-purple-400',
  },
  {
    id: 'gemini',
    label: 'Gemini',
    description: 'Gemini 2.5 Flash — multimodal',
    activeColor: 'border-blue-400/20 text-blue-400',
  },
];

const localModels: ModelDef[] = [
  {
    id: 'stark_protocol',
    label: 'Stark Protocol',
    description: 'Self-hosted Gemma 3 — private',
    activeColor: 'border-red-400/20 text-red-400',
  },
];

function ModelButton({
  model,
  isSelected,
  onSelect,
}: {
  model: ModelDef;
  isSelected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={clsx(
        'w-full text-left px-4 py-2.5 transition-all rounded-xl border',
        isSelected
          ? `bg-white/[0.04] ${model.activeColor}`
          : 'bg-transparent border-white/[0.04] text-gray-400 hover:bg-white/[0.03]',
      )}
    >
      <div className="flex items-center justify-between">
        <span className={clsx('text-xs font-medium', isSelected ? '' : 'text-gray-300')}>
          {model.label}
        </span>
        {isSelected && (
          <div className="w-2 h-2 rounded-full bg-current shadow-[0_0_6px_currentColor]" />
        )}
      </div>
      <p className="text-[10px] text-gray-600 mt-0.5 font-mono">{model.description}</p>
    </button>
  );
}

export default function ModelPicker() {
  const { modelPreference, setModelPreference } = useSettingsStore();

  return (
    <div className="space-y-3">
      <div>
        <span className="hud-label text-[8px] block mb-1.5">UPLINK</span>
        <div className="space-y-1.5">
          {uplinkModels.map((model) => (
            <ModelButton
              key={model.id}
              model={model}
              isSelected={modelPreference === model.id}
              onSelect={() => setModelPreference(model.id)}
            />
          ))}
        </div>
      </div>

      <div>
        <span className="hud-label text-[8px] block mb-1.5">LOCAL</span>
        <div className="space-y-1.5">
          {localModels.map((model) => (
            <ModelButton
              key={model.id}
              model={model}
              isSelected={modelPreference === model.id}
              onSelect={() => setModelPreference(model.id)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
