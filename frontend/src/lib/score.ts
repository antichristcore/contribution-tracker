import type { ScoreComponent, ScoreComponentKey } from "./types";

/** Подписи компонент живут здесь, а не на бэке: оттуда приходят только числа
 *  и ключи, чтобы формулировки можно было менять, не трогая расчёт. */
export const COMPONENT_LABELS: Record<ScoreComponentKey, string> = {
  tasks: "Задачи в срок",
  code: "Код",
  rhythm: "Ритм",
  reviews: "Ревью",
  penalty: "Застой",
};

function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}

export function days(n: number): string {
  return `${n} ${plural(n, "день", "дня", "дней")}`;
}

/** Разряды пробелами: «3 420 строк» читается, «3420» — нет. */
export function num(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("ru-RU");
}

/** Строка под названием компоненты: откуда взялось её значение. */
export function componentDetail(c: ScoreComponent): string {
  if (c.excluded) return excludedReason(c.key);

  switch (c.key) {
    case "tasks":
      return `${c.done_on_time} из ${c.eligible} закрыто до дедлайна`;
    case "code":
      return `${num(c.raw_value)} строк за неделю, медиана по команде ${num(c.peer_median)}`;
    case "rhythm":
      return `${days(c.active_days ?? 0)} с коммитами из ${c.window_days}, для полного балла нужно ${c.target_days}`;
    case "reviews":
      return `${c.raw_value} ревью, медиана ${num(c.peer_median)}`;
    case "penalty":
      return c.stuck_days
        ? `задача без изменений ${days(c.stuck_days)}`
        : "застрявших задач нет";
  }
}

function excludedReason(key: ScoreComponentKey): string {
  if (key === "reviews") return "в команде нет пул-реквестов — вес ушёл остальным";
  if (key === "tasks") return "нет задач с наступившим сроком — вес ушёл остальным";
  return "не учитывается";
}

/** Пояснения-сноски под разбором. Ключи приходят с бэка. */
export const NOTE_TEXTS: Record<string, string> = {
  code_capped:
    "Вклад в код выше двух медиан дальше не растёт — иначе один сгенерированный файл делал бы автора лучшим в команде.",
  reviews_excluded:
    "Команда коммитит без пул-реквестов, поэтому ревью не участвует в расчёте, а не обнуляет балл.",
  tasks_excluded:
    "Задач с наступившим сроком пока нет. Компонента исключена: не назначили задачу — не за что снижать балл.",
  peer_fallback_team:
    "В этой роли не с кем сравнивать, поэтому медиана считается по всей команде.",
};
