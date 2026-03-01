import { useSettingsStore, ModelProvider } from '@/stores/settingsStore';
import clsx from 'clsx';

const models: { id: ModelProvider; label: string; description: string; color: string }[] = [
  {
    id: 'openai',
    label: 'OpenAI',
    description: 'GPT-4o — versatile, fast, vision-capable',
    color: 'from-green-400/20 to-green-600/10 border-green-400/30 text-green-400',
  },
  {
    id: 'claude',
    label: 'Claude',
    description: 'Sonnet 4 — nuanced reasoning, long context',
    color: 'from-orange-400/20 to-orange-600/10 border-orange-400/30 text-orange-400',
  },
  {
    id: 'gemini',
    label: 'Gemini',
    description: 'Gemini 2.5 Flash — fast, multimodal',
    color: 'from-blue-400/20 to-blue-600/10 border-blue-400/30 text-blue-400',
  },
  {
    id: 'stark_protocol',
    label: 'Stark Protocol',
    description: 'Self-hosted Gemma 3 — private, no data leaves',
    color: 'from-red-400/20 to-red-600/10 border-red-400/30 text-red-400',
  },
];

export default function ModelPicker() {
  const { modelPreference, setModelPreference } = useSettingsStore();

  return (
    <div className="space-y-2">
      {models.map((model) => {
        const isSelected = modelPreference === model.id;
        return (
          <button
            key={model.id}
            onClick={() => setModelPreference(model.id)}
            className={clsx(
              'w-full text-left px-3 py-2.5 rounded-lg transition-all border',
              isSelected
                ? `bg-gradient-to-r ${model.color}`
                : 'bg-transparent border-transparent text-gray-400 hover:bg-white/[0.03]'
            )}
          >
            <div className="flex items-center justify-between">
              <span className={clsx('text-sm font-medium', isSelected ? '' : 'text-gray-300')}>
                {model.label}
              </span>
              {isSelected && (
                <div className="w-2 h-2 rounded-full bg-current" />
              )}
            </div>
            <p className="text-[11px] text-gray-500 mt-0.5">{model.description}</p>
          </button>
        );
      })}
    </div>
  );
}
