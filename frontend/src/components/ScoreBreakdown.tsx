import { COMPONENT_LABELS, NOTE_TEXTS, componentDetail } from "../lib/score";
import type { ScoreBreakdown as Breakdown } from "../lib/types";

interface Props {
  breakdown: Breakdown;
  scoreMax?: number;
  onExplain: () => void;
}

function signed(points: number): string {
  const rounded = Math.round(points * 10) / 10;
  if (rounded === 0) return "0";
  return `${rounded > 0 ? "+" : "−"}${Math.abs(rounded)}`;
}

/** Разбор балла на слагаемые: что именно дало эти 65 из 100.
 *
 *  Числа приходят из того же кода, который считает сам балл, — иначе экран
 *  «как это считается» начал бы врать убедительнее, чем молчание. */
export default function ScoreBreakdown({ breakdown, scoreMax = 100, onExplain }: Props) {
  return (
    <div className="mb-4 rounded-2xl bg-[var(--tg-section-bg-color)] p-3">
      <div className="mb-3 flex items-baseline gap-1.5">
        <span className="text-3xl font-bold text-[var(--tg-text-color)]">{breakdown.score}</span>
        <span className="text-sm text-[var(--tg-hint-color)]">из {scoreMax}</span>
      </div>

      <div className="mb-2 space-y-2">
        {breakdown.components.map((c) => (
          <div key={c.key} className={c.excluded ? "opacity-55" : ""}>
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-sm font-medium text-[var(--tg-text-color)]">
                {COMPONENT_LABELS[c.key]}
              </span>
              <span className="flex shrink-0 items-baseline gap-2">
                {!c.excluded && (
                  <span className="text-[10px] text-[var(--tg-hint-color)]">
                    макс. {Math.round(Math.abs(c.weight))}
                  </span>
                )}
                <span
                  className={`w-10 text-right text-sm font-semibold tabular-nums ${
                    c.excluded
                      ? "text-[var(--tg-hint-color)]"
                      : c.points < 0
                        ? "text-red-500"
                        : "text-emerald-500"
                  }`}
                >
                  {c.excluded ? "—" : signed(c.points)}
                </span>
              </span>
            </div>
            <div className="text-[11px] leading-snug text-[var(--tg-hint-color)]">
              {componentDetail(c)}
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-baseline justify-between border-t border-[var(--tg-secondary-bg-color)] pt-2">
        <span className="text-sm font-semibold text-[var(--tg-text-color)]">Итого</span>
        <span className="text-sm font-bold text-[var(--tg-text-color)]">{breakdown.score}</span>
      </div>

      {breakdown.notes.length > 0 && (
        <div className="mt-2 space-y-1">
          {breakdown.notes.map((n) => (
            <div key={n} className="text-[11px] leading-snug text-[var(--tg-hint-color)]">
              {NOTE_TEXTS[n] ?? n}
            </div>
          ))}
        </div>
      )}

      <button onClick={onExplain} className="mt-3 text-xs text-[var(--tg-link-color)]">
        Откуда эти числа →
      </button>
    </div>
  );
}
