import type { StatusColor } from "./types";

export const STATUS_META: Record<StatusColor, { label: string; dot: string; ring: string; text: string }> = {
  green: { label: "В норме", dot: "bg-emerald-500", ring: "ring-emerald-500/30", text: "text-emerald-500" },
  yellow: { label: "Требует внимания", dot: "bg-amber-400", ring: "ring-amber-400/40", text: "text-amber-500" },
  red: { label: "Тревога", dot: "bg-red-500", ring: "ring-red-500/40", text: "text-red-500" },
  no_data: { label: "Нет данных", dot: "bg-gray-400", ring: "ring-gray-400/30", text: "text-gray-400" },
};

export const TASK_STATUS_META: Record<string, { label: string; className: string }> = {
  todo: { label: "К выполнению", className: "bg-gray-500/15 text-gray-500" },
  in_progress: { label: "В работе", className: "bg-blue-500/15 text-blue-500" },
  done: { label: "Готово", className: "bg-emerald-500/15 text-emerald-600" },
};

export function formatScore(score: number | null): string {
  if (score === null || score === undefined) return "—";
  return score.toFixed(2);
}

// Роль хранится ключом ("ba"), показывать её надо словами. Незнакомый ключ
// возвращаем как есть: роли задавались вручную и до появления этого списка.
export const ROLE_LABELS: Record<string, string> = {
  backend: "Backend",
  frontend: "Frontend",
  design: "Design",
  qa: "QA",
  pm: "PM",
  ba: "Бизнес-аналитик",
  sa: "Системный аналитик",
  devops: "DevOps",
  teamlead: "Тимлид",
  member: "Участник",
};

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}
