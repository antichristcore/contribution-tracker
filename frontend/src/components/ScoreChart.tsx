import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ScoreHistoryPoint } from "../lib/types";

interface Props {
  history: ScoreHistoryPoint[];
}

export default function ScoreChart({ history }: Props) {
  const data = history.map((h) => ({
    date: h.computed_at.slice(5, 10),
    score: h.contribution_score,
  }));

  if (data.length < 2) {
    return (
      <div className="text-sm text-[var(--tg-hint-color)] py-6 text-center">
        Для графика нужно хотя бы пару дней истории, пока их меньше.
      </div>
    );
  }

  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--tg-hint-color)" opacity={0.15} />
          <XAxis dataKey="date" tick={{ fontSize: 11, fill: "var(--tg-hint-color)" }} />
          {/* Шкала фиксирована: иначе Recharts подгоняет ось под данные,
              и колебание 70..75 рисуется как американские горки. */}
          <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: "var(--tg-hint-color)" }} width={36} />
          <Tooltip
            contentStyle={{
              background: "var(--tg-section-bg-color)",
              border: "none",
              borderRadius: 12,
              color: "var(--tg-text-color)",
              fontSize: 12,
            }}
          />
          <Line
            type="monotone"
            dataKey="score"
            stroke="var(--tg-button-color)"
            strokeWidth={2}
            dot={{ r: 2 }}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
