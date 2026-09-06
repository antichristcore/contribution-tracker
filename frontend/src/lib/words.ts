/** Согласование слов с числами. Без него интерфейс пишет «191 коммитов»
 *  и «1 дней», а такие мелочи читаются как небрежность во всём остальном. */

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

export function commits(n: number): string {
  return `${n} ${plural(n, "коммит", "коммита", "коммитов")}`;
}

export function people(n: number): string {
  return `${n} ${plural(n, "человек", "человека", "человек")}`;
}

/** Разряды пробелами: «3 420 строк» читается, «3420» — нет. */
export function num(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("ru-RU");
}
