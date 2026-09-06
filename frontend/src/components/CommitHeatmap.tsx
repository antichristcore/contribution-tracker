import { useEffect, useState } from "react";
import CommitCard from "./CommitCard";
import { api } from "../lib/api";
import { commits as commitsWord, days as daysWord } from "../lib/words";
import type { CommitInfo } from "../lib/types";

interface ActivityDay {
  date: string;
  commits: number;
  lines: number;
}

interface Activity {
  days: ActivityDay[];
  max_commits: number;
  total_commits: number;
  total_lines: number;
}

interface Props {
  /** Без него — активность всей команды. */
  memberId?: number;
  days?: number;
}

const CELL = 11;
const GAP = 2;
const WEEKDAYS = ["Пн", "", "Ср", "", "Пт", "", ""];
const MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

/** Пять ступеней, как на GitHub: пусто и четыре уровня насыщенности. */
function levelOf(commits: number, max: number): number {
  if (commits === 0) return 0;
  if (max <= 1) return 4;
  const share = commits / max;
  if (share <= 0.25) return 1;
  if (share <= 0.5) return 2;
  if (share <= 0.75) return 3;
  return 4;
}

const LEVEL_COLORS = [
  "var(--tg-secondary-bg-color)",
  "#9be9a8",
  "#40c463",
  "#30a14e",
  "#216e39",
];

function formatDay(date: string): string {
  return new Date(`${date}T00:00:00`).toLocaleDateString("ru-RU");
}

/** Календарь коммитов в стиле GitHub. Рисуется вручную на SVG: подключать
 *  ради него график-библиотеку нельзя — она в пять раз тяжелее приложения.
 *  Тап по клетке открывает коммиты этого дня. */
export default function CommitHeatmap({ memberId, days = 91 }: Props) {
  const [data, setData] = useState<Activity | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ActivityDay | null>(null);
  const [dayCommits, setDayCommits] = useState<CommitInfo[] | null>(null);
  const [dayError, setDayError] = useState<string | null>(null);

  useEffect(() => {
    const query = `?days=${days}${memberId != null ? `&member_id=${memberId}` : ""}`;
    api
      .get<Activity>(`/scores/commit-activity${query}`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Не удалось загрузить активность"));
  }, [memberId, days]);

  async function openDay(cell: ActivityDay) {
    if (selected?.date === cell.date) {
      setSelected(null);
      return;
    }
    setSelected(cell);
    setDayCommits(null);
    setDayError(null);
    // Пустой день грузить нечего — и так видно, что коммитов не было.
    if (cell.commits === 0) return;
    try {
      const query = `?date=${cell.date}${memberId != null ? `&member_id=${memberId}` : ""}`;
      setDayCommits(await api.get<CommitInfo[]>(`/scores/commit-activity/day${query}`));
    } catch (e) {
      setDayError(e instanceof Error ? e.message : "Не удалось загрузить коммиты дня");
    }
  }

  if (error) return <div className="text-xs text-red-500">{error}</div>;
  if (!data) return <div className="h-24 text-xs text-[var(--tg-hint-color)]">Загрузка...</div>;

  // Дополняем начало пустыми клетками, чтобы первая неделя начиналась с понедельника.
  const first = new Date(`${data.days[0].date}T00:00:00`);
  const pad = (first.getDay() + 6) % 7;
  const cells: (ActivityDay | null)[] = [...Array(pad).fill(null), ...data.days];
  const weeks = Math.ceil(cells.length / 7);

  const width = weeks * (CELL + GAP);
  const height = 7 * (CELL + GAP);

  // Подпись месяца ставим над неделей, в которой месяц начался.
  const monthMarks: { x: number; label: string }[] = [];
  let lastMonth = -1;
  for (let w = 0; w < weeks; w++) {
    const cell = cells[w * 7];
    if (!cell) continue;
    const month = new Date(`${cell.date}T00:00:00`).getMonth();
    if (month !== lastMonth) {
      monthMarks.push({ x: w * (CELL + GAP), label: MONTHS[month] });
      lastMonth = month;
    }
  }

  return (
    <div>
      <div className="mb-1.5 text-[11px] text-[var(--tg-hint-color)]">
        {commitsWord(data.total_commits)} за {daysWord(days)}. Нажми на день, чтобы посмотреть какие.
      </div>

      <div className="overflow-x-auto">
        <svg width={width + 24} height={height + 14} className="block">
          {monthMarks.map((m) => (
            <text
              key={m.label + m.x}
              x={m.x + 24}
              y={9}
              className="fill-[var(--tg-hint-color)]"
              fontSize="9"
            >
              {m.label}
            </text>
          ))}
          {WEEKDAYS.map((label, i) =>
            label ? (
              <text
                key={i}
                x={0}
                y={14 + i * (CELL + GAP) + CELL - 2}
                className="fill-[var(--tg-hint-color)]"
                fontSize="8"
              >
                {label}
              </text>
            ) : null
          )}
          {cells.map((cell, i) => {
            if (!cell) return null;
            const week = Math.floor(i / 7);
            const weekday = i % 7;
            const isSelected = selected?.date === cell.date;
            return (
              <rect
                key={cell.date}
                x={week * (CELL + GAP) + 24}
                y={14 + weekday * (CELL + GAP)}
                width={CELL}
                height={CELL}
                rx={2}
                fill={LEVEL_COLORS[levelOf(cell.commits, data.max_commits)]}
                stroke={isSelected ? "var(--tg-link-color)" : "none"}
                strokeWidth={isSelected ? 1.5 : 0}
                className="cursor-pointer"
                onClick={() => void openDay(cell)}
              />
            );
          })}
        </svg>
      </div>

      <div className="mt-1.5 flex items-center justify-end gap-1 text-[10px] text-[var(--tg-hint-color)]">
        меньше
        {LEVEL_COLORS.map((c) => (
          <span key={c} className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: c }} />
        ))}
        больше
      </div>

      {selected && (
        <div className="mt-3 border-t border-[var(--tg-secondary-bg-color)] pt-3">
          <div className="mb-2 flex items-baseline justify-between gap-2">
            <span className="text-sm font-semibold text-[var(--tg-text-color)]">
              {formatDay(selected.date)}
            </span>
            <span className="shrink-0 text-[11px] text-[var(--tg-hint-color)]">
              {selected.commits === 0
                ? "коммитов не было"
                : `${commitsWord(selected.commits)}, ${selected.lines} строк`}
            </span>
          </div>

          {dayError && <div className="text-xs text-red-500">{dayError}</div>}
          {selected.commits > 0 && !dayCommits && !dayError && (
            <div className="text-xs text-[var(--tg-hint-color)]">Загрузка...</div>
          )}
          {dayCommits?.map((c) => <CommitCard key={c.id} commit={c} showTask />)}
        </div>
      )}
    </div>
  );
}
