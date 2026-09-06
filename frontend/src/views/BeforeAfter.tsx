import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../lib/api";
import { formatScore } from "../lib/status";
import type { BeforeAfterData } from "../lib/types";

interface Props {
  onBack: () => void;
}

// One colour per member — the demo team has 8, and repeats made two people
// on the chart look like the same line.
const LINE_COLORS = [
  "#2481cc",
  "#34c759",
  "#ff9500",
  "#ff3b30",
  "#af52de",
  "#00c7be",
  "#ff2d55",
  "#a2845e",
];

type BeforeAfterMember = BeforeAfterData["members"][number];

/** Score at the end of the window — the "после" value the screen is about. */
function currentScore(member: BeforeAfterMember): number | null {
  for (let i = member.series.length - 1; i >= 0; i--) {
    const score = member.series[i]?.score;
    if (score !== null && score !== undefined) return score;
  }
  return null;
}

/** Best score first, so the legend and the line colours follow the ranking.
 *  People without any data go last rather than being treated as a zero. */
function byScoreDesc(a: BeforeAfterMember, b: BeforeAfterMember): number {
  const sa = currentScore(a);
  const sb = currentScore(b);
  if (sa === null && sb === null) return a.display_name.localeCompare(b.display_name, "ru");
  if (sa === null) return 1;
  if (sb === null) return -1;
  return sb - sa;
}

export default function BeforeAfter({ onBack }: Props) {
  const [data, setData] = useState<BeforeAfterData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<BeforeAfterData>("/presentation/before-after")
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Не удалось загрузить данные"));
  }, []);

  if (error) return <div className="p-4 text-sm text-red-500">{error}</div>;
  if (!data) return <div className="p-6 text-center text-[var(--tg-hint-color)]">Загрузка...</div>;

  const members = [...data.members].sort(byScoreDesc);

  const chartData = data.days.map((date, i) => {
    const row: Record<string, string | number | null> = {
      date: date.slice(5),
      median: data.team_median_by_day[i]?.median ?? null,
    };
    for (const m of members) {
      row[m.display_name] = m.series[i]?.score ?? null;
    }
    return row;
  });

  return (
    <div className="p-4 pb-10">
      <button onClick={onBack} className="mb-4 text-sm text-[var(--tg-link-color)]">
        ← Назад
      </button>
      <h1 className="mb-1 text-xl font-bold text-[var(--tg-text-color)]">Динамика команды</h1>
      <p className="mb-4 text-xs text-[var(--tg-hint-color)]">
        Как менялся вклад каждого за три недели и когда срабатывали пороги. Шкала — 0..100.
      </p>

      <div className="mb-4 rounded-2xl bg-[var(--tg-section-bg-color)] p-3">
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 0, left: -20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--tg-hint-color)" opacity={0.15} />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--tg-hint-color)" }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "var(--tg-hint-color)" }} width={32} />
              <Tooltip
                // Highest score first, same ranking the legend shows.
                itemSorter={(item) => -(Number(item.value) || 0)}
                contentStyle={{
                  background: "var(--tg-bg-color)",
                  border: "none",
                  borderRadius: 12,
                  fontSize: 11,
                }}
              />
              <Line type="monotone" dataKey="median" stroke="#8e8e93" strokeDasharray="4 4" dot={false} name="медиана" />
              {members.map((m, i) => (
                <Line
                  key={m.member_id}
                  type="monotone"
                  dataKey={m.display_name}
                  stroke={LINE_COLORS[i % LINE_COLORS.length]}
                  strokeWidth={2}
                  dot={{ r: 1.5 }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Own legend instead of <Legend>: Recharts 3 builds its legend from an
            internal store and rendered the names alphabetically, ignoring the
            order the lines are declared in. */}
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
          {members.map((m, i) => {
            const score = currentScore(m);
            return (
              <span key={m.member_id} className="flex items-center gap-1">
                <span
                  className="inline-block h-2 w-2 shrink-0 rounded-full"
                  style={{ background: LINE_COLORS[i % LINE_COLORS.length] }}
                />
                <span className="text-[var(--tg-text-color)]">{m.display_name}</span>
                <span className="text-[var(--tg-hint-color)]">
                  {score === null ? "нет данных" : formatScore(score)}
                </span>
              </span>
            );
          })}
          <span className="flex items-center gap-1">
            <span className="inline-block h-0.5 w-3 shrink-0" style={{ background: "#8e8e93" }} />
            <span className="text-[var(--tg-hint-color)]">медиана</span>
          </span>
        </div>
      </div>

      <div className="mb-2 text-sm font-semibold text-[var(--tg-text-color)]">События</div>
      {data.notifications.length === 0 && (
        <div className="text-sm text-[var(--tg-hint-color)]">Пока не было срабатываний порогов.</div>
      )}
      {data.notifications.map((n, i) => (
        <div key={i} className="mb-2 rounded-xl bg-[var(--tg-section-bg-color)] p-3 text-sm">
          <div className="font-medium text-[var(--tg-text-color)]">
            {n.type === "red_threshold" ? "🔴 Красный порог" : n.type === "yellow_threshold" ? "🟡 Жёлтый порог" : "📋 Задача назначена"}
          </div>
          <div className="text-xs text-[var(--tg-hint-color)]">
            {new Date(n.sent_at).toLocaleString("ru-RU")} {n.payload_summary ? `· ${n.payload_summary}` : ""}
          </div>
        </div>
      ))}
    </div>
  );
}
