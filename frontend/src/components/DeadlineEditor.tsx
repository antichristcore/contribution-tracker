import { useState } from "react";
import { haptic } from "../lib/telegram";

interface Props {
  deadlineAt: string | null;
  onChange: (deadlineAt: string | null) => Promise<void>;
  onClose: () => void;
}

/** Перенос срока: быстрые сдвиги на N дней плюс выбор конкретной даты.
 *  Сдвиг считается от текущего дедлайна, а у задачи без срока — от сегодня. */
const QUICK_SHIFTS: { label: string; days: number }[] = [
  { label: "+1 день", days: 1 },
  { label: "+3 дня", days: 3 },
  { label: "+ неделя", days: 7 },
];

function toDateInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  // Локальная дата, а не UTC: иначе вечером сдвигается на день назад.
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

export default function DeadlineEditor({ deadlineAt, onChange, onClose }: Props) {
  const [date, setDate] = useState(toDateInput(deadlineAt));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function apply(next: string | null) {
    setBusy(true);
    setError(null);
    try {
      await onChange(next);
      haptic("success");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось перенести срок");
      setBusy(false);
    }
  }

  function shiftBy(days: number) {
    const base = deadlineAt ? new Date(deadlineAt) : new Date();
    base.setDate(base.getDate() + days);
    void apply(base.toISOString());
  }

  return (
    <div className="mb-3 rounded-xl bg-[var(--tg-secondary-bg-color)] p-3">
      <div className="mb-2 text-xs font-medium text-[var(--tg-text-color)]">Перенести срок</div>

      <div className="mb-2 flex flex-wrap gap-1.5">
        {QUICK_SHIFTS.map((s) => (
          <button
            key={s.days}
            onClick={() => shiftBy(s.days)}
            disabled={busy}
            className="rounded-full bg-[var(--tg-bg-color)] px-3 py-1.5 text-xs text-[var(--tg-text-color)] active:scale-95 transition-transform disabled:opacity-50"
          >
            {s.label}
          </button>
        ))}
      </div>

      <div className="flex gap-2">
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="flex-1 rounded-lg bg-[var(--tg-bg-color)] px-3 py-2 text-sm text-[var(--tg-text-color)] outline-none"
        />
        <button
          onClick={() => apply(date ? new Date(`${date}T12:00:00`).toISOString() : null)}
          disabled={busy}
          className="rounded-lg bg-[var(--tg-button-color)] px-4 py-2 text-sm font-medium text-[var(--tg-button-text-color)] active:scale-95 transition-transform disabled:opacity-60"
        >
          {busy ? "..." : "ОК"}
        </button>
      </div>

      <div className="mt-2 flex justify-between text-xs">
        {deadlineAt ? (
          <button onClick={() => apply(null)} disabled={busy} className="text-red-500 disabled:opacity-50">
            Убрать срок
          </button>
        ) : (
          <span />
        )}
        <button onClick={onClose} disabled={busy} className="text-[var(--tg-hint-color)]">
          Отмена
        </button>
      </div>

      {error && <div className="mt-2 text-xs text-red-500">{error}</div>}
    </div>
  );
}
