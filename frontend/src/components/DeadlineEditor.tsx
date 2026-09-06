import { useState } from "react";
import { haptic } from "../lib/telegram";

interface Props {
  deadlineAt: string | null;
  onChange: (deadlineAt: string | null) => Promise<void>;
  onClose: () => void;
}

/** Готовые сдвиги на частые случаи. Всё остальное — полем «через N дней»
 *  и точной датой со временем. */
const QUICK_SHIFTS: { label: string; days: number }[] = [
  { label: "+1 день", days: 1 },
  { label: "+3 дня", days: 3 },
  { label: "+ неделя", days: 7 },
  { label: "+ 2 недели", days: 14 },
];

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** Локальные дата и время, а не UTC: вечером UTC-срез уезжает на день назад. */
function splitLocal(iso: string | null): { date: string; time: string } {
  if (!iso) return { date: "", time: "18:00" };
  const d = new Date(iso);
  return {
    date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
    time: `${pad(d.getHours())}:${pad(d.getMinutes())}`,
  };
}

export default function DeadlineEditor({ deadlineAt, onChange, onClose }: Props) {
  const initial = splitLocal(deadlineAt);
  const [date, setDate] = useState(initial.date);
  const [time, setTime] = useState(initial.time);
  const [customDays, setCustomDays] = useState("");
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

  /** Сдвиг от текущего срока, а у задачи без срока — от сегодняшнего дня.
   *  Время сохраняем прежнее, чтобы перенос не сбрасывал его на полночь. */
  function shiftBy(days: number) {
    const base = deadlineAt ? new Date(deadlineAt) : new Date();
    if (!deadlineAt) base.setHours(18, 0, 0, 0);
    base.setDate(base.getDate() + days);
    void apply(base.toISOString());
  }

  function applyExact() {
    if (!date) {
      void apply(null);
      return;
    }
    void apply(new Date(`${date}T${time || "18:00"}:00`).toISOString());
  }

  const customValid = /^\d{1,3}$/.test(customDays) && Number(customDays) > 0;

  return (
    <div className="mb-3 rounded-xl bg-[var(--tg-secondary-bg-color)] p-3">
      <div className="mb-2 text-xs font-medium text-[var(--tg-text-color)]">Срок задачи</div>

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

      <div className="mb-2 flex items-center gap-2">
        <span className="text-xs text-[var(--tg-hint-color)]">или через</span>
        <input
          inputMode="numeric"
          placeholder="N"
          value={customDays}
          onChange={(e) => setCustomDays(e.target.value.replace(/\D/g, ""))}
          className="w-16 rounded-lg bg-[var(--tg-bg-color)] px-2 py-1.5 text-center text-sm text-[var(--tg-text-color)] outline-none"
        />
        <span className="text-xs text-[var(--tg-hint-color)]">дн.</span>
        <button
          onClick={() => shiftBy(Number(customDays))}
          disabled={busy || !customValid}
          className="rounded-lg bg-[var(--tg-bg-color)] px-3 py-1.5 text-xs text-[var(--tg-text-color)] disabled:opacity-40"
        >
          Сдвинуть
        </button>
      </div>

      <div className="mb-2 flex gap-2">
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="flex-1 rounded-lg bg-[var(--tg-bg-color)] px-3 py-2 text-sm text-[var(--tg-text-color)] outline-none"
        />
        <input
          type="time"
          value={time}
          onChange={(e) => setTime(e.target.value)}
          className="w-28 rounded-lg bg-[var(--tg-bg-color)] px-3 py-2 text-sm text-[var(--tg-text-color)] outline-none"
        />
        <button
          onClick={applyExact}
          disabled={busy}
          className="rounded-lg bg-[var(--tg-button-color)] px-4 py-2 text-sm font-medium text-[var(--tg-button-text-color)] active:scale-95 transition-transform disabled:opacity-60"
        >
          {busy ? "..." : "ОК"}
        </button>
      </div>

      <div className="flex justify-between text-xs">
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
