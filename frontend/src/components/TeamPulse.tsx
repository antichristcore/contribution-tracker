import type { TeamSummary } from "../lib/types";
import { formatScore } from "../lib/status";

interface Props {
  summary: TeamSummary;
  onExplain: () => void;
}

const SEGMENTS: { key: keyof TeamSummary; color: string; label: string }[] = [
  { key: "green_count", color: "bg-emerald-500", label: "в норме" },
  { key: "yellow_count", color: "bg-amber-400", label: "внимание" },
  { key: "red_count", color: "bg-red-500", label: "тревога" },
  { key: "no_data_count", color: "bg-gray-400", label: "нет данных" },
];

export default function TeamPulse({ summary, onExplain }: Props) {
  const total =
    summary.green_count + summary.yellow_count + summary.red_count + summary.no_data_count || 1;

  return (
    <div className="mb-4 rounded-2xl bg-[var(--tg-section-bg-color)] p-4 fade-in-up">
      <div className="mb-3 flex items-end justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-[var(--tg-hint-color)]">
            Пульс команды
          </div>
          <div className="text-2xl font-bold text-[var(--tg-text-color)]">
            {formatScore(summary.median_score)}
            <span className="ml-1.5 text-xs font-normal text-[var(--tg-hint-color)]">
              середина команды
            </span>
          </div>
        </div>
        <button
          onClick={onExplain}
          aria-label="Как считается вклад"
          className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--tg-secondary-bg-color)] text-sm text-[var(--tg-hint-color)] active:scale-90 transition-transform"
        >
          ?
        </button>
      </div>

      <div className="mb-3 flex h-2.5 w-full overflow-hidden rounded-full bg-[var(--tg-secondary-bg-color)]">
        {SEGMENTS.map((s) => {
          const value = summary[s.key] as number;
          if (!value) return null;
          return (
            <div
              key={s.key}
              className={`${s.color} h-full transition-all`}
              style={{ width: `${(value / total) * 100}%` }}
            />
          );
        })}
      </div>

      <div className="mb-1.5 text-[10px] text-[var(--tg-hint-color)]">
        тимлид в этот подсчёт не входит
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {SEGMENTS.map((s) => (
          <div key={s.key} className="flex items-center gap-1.5 text-xs text-[var(--tg-hint-color)]">
            <span className={`h-2 w-2 rounded-full ${s.color}`} />
            {summary[s.key] as number} {s.label}
          </div>
        ))}
      </div>
    </div>
  );
}
