import type { ScoreComponent, ScoreComponentKey } from "./types";
import { days, num } from "./words";

/** Подписи строк разбора живут здесь, а не на бэке: оттуда приходят только
 *  числа и ключи, чтобы формулировки можно было менять, не трогая расчёт. */
export const COMPONENT_LABELS: Record<ScoreComponentKey, string> = {
  tasks: "Задачи в срок",
  code: "Код",
  rhythm: "Ритм",
  reviews: "Ревью",
  penalty: "Задачи без движения",
};

/** Строка под названием: откуда взялось значение.
 *
 *  «Медиану» здесь называем серединой команды. Слово точное, но половина
 *  пользователей его не знает, а объяснение балла не должно требовать
 *  объяснения слов. */
export function componentDetail(c: ScoreComponent): string {
  if (c.excluded) return excludedReason(c.key);

  switch (c.key) {
    case "tasks":
      return `${c.done_on_time} из ${c.eligible} сдано до дедлайна`;
    case "code":
      return `${num(c.raw_value)} строк за неделю, середина команды ${num(c.peer_median)}`;
    case "rhythm":
      return `${days(c.active_days ?? 0)} с коммитами из ${c.window_days}, на полный балл нужно ${c.target_days}`;
    case "reviews":
      return `${c.raw_value} ревью, середина команды ${num(c.peer_median)}`;
    case "penalty":
      return c.stuck_days
        ? `самая застоявшаяся задача стоит ${days(c.stuck_days)}`
        : "всё в движении, штрафа нет";
  }
}

function excludedReason(key: ScoreComponentKey): string {
  if (key === "reviews") return "команда работает без пул-реквестов, баллы ушли в другие строки";
  if (key === "tasks") return "задач с наступившим сроком пока нет, баллы ушли в другие строки";
  return "не считается";
}

/** Сноски под разбором. Ключи приходят с бэка. */
export const NOTE_TEXTS: Record<string, string> = {
  code_capped:
    "Больше двух середин команды за код не начисляем. Иначе один залитый сгенерированный файл сделал бы автора первым в команде.",
  reviews_excluded:
    "Команда работает без пул-реквестов, поэтому строка «Ревью» не считается. Её баллы разошлись по другим строкам, а не пропали.",
  tasks_excluded:
    "Задач с наступившим сроком пока нет, поэтому строка «Задачи в срок» не считается. Её баллы разошлись по другим строкам: за то, что задачу не назначили, балл снижать не за что.",
  peer_fallback_team:
    "В этой роли сравнивать не с кем, поэтому сравниваем со всей командой.",
};
