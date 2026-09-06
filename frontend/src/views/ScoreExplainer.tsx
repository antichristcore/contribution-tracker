import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { days } from "../lib/score";
import type { ScoreFormula } from "../lib/types";

interface Props {
  onBack: () => void;
}

/** Экран «Как считается вклад».
 *
 *  Числа приходят с бэка (`/scores/formula`), а не забиты в текст: копия
 *  констант в вёрстке разъехалась бы с расчётом за первую же правку весов —
 *  и объяснение стало бы хуже, чем его отсутствие. */
export default function ScoreExplainer({ onBack }: Props) {
  const [f, setF] = useState<ScoreFormula | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<ScoreFormula>("/scores/formula")
      .then(setF)
      .catch((e) => setError(e instanceof Error ? e.message : "Не удалось загрузить формулу"));
  }, []);

  if (error) return <div className="p-4 text-sm text-red-500">{error}</div>;
  if (!f) return <div className="p-6 text-center text-[var(--tg-hint-color)]">Загрузка...</div>;

  const rows = [
    {
      label: "Задачи в срок",
      weight: f.weight_tasks,
      text: `Доля задач, закрытых до дедлайна. Считаются только те, по которым срок уже наступил: задача без дедлайна и задача со сроком в будущем не влияют ни в плюс, ни в минус. Срок сравнивается по дню — закрыл в день дедлайна, значит в срок.`,
    },
    {
      label: "Код",
      weight: f.weight_code,
      text: `Строки, изменённые за ${days(f.code_window_days)}, относительно медианы команды. Медиана даёт половину веса, вдвое больше медианы — весь вес. Один коммит засчитывается не больше чем в ${f.max_lines_per_commit.toLocaleString("ru-RU")} строк.`,
    },
    {
      label: "Ритм",
      weight: f.weight_rhythm,
      text: `Сколько дней из ${f.rhythm_window_days} были с коммитами. ${f.rhythm_target_days} дней — полный вес. Отличает ровную работу от аврала в ночь перед сдачей: объём кода может совпасть, а работа — нет.`,
    },
    {
      label: "Ревью",
      weight: f.weight_reviews,
      text: `Комментарии в чужих пул-реквестах, тоже относительно медианы. Если команда работает без пул-реквестов, компонента исключается целиком, а её вес расходится по остальным.`,
    },
    {
      label: "Застой",
      weight: -f.penalty_max,
      text: `Штраф за задачу, по которой давно нет изменений. Растёт линейно и упирается в потолок на ${days(f.stuck_red_days)}.`,
    },
  ];

  return (
    <div className="p-4 pb-10">
      <button onClick={onBack} className="mb-4 text-sm text-[var(--tg-link-color)]">
        ← Назад
      </button>

      <h1 className="mb-1 text-xl font-bold text-[var(--tg-text-color)]">Как считается вклад</h1>
      <p className="mb-4 text-xs leading-relaxed text-[var(--tg-hint-color)]">
        Балл — целое от 0 до {f.score_max}. Он складывается из четырёх слагаемых и одного штрафа.
        Ничего из этого участник о себе не сообщает: всё считается из истории git и доски задач.
      </p>

      <div className="mb-4 space-y-2">
        {rows.map((r) => (
          <div key={r.label} className="rounded-2xl bg-[var(--tg-section-bg-color)] p-3">
            <div className="mb-1 flex items-baseline justify-between gap-2">
              <span className="text-sm font-semibold text-[var(--tg-text-color)]">{r.label}</span>
              <span
                className={`shrink-0 text-sm font-bold tabular-nums ${
                  r.weight < 0 ? "text-red-500" : "text-emerald-500"
                }`}
              >
                {r.weight > 0 ? `до +${r.weight}` : `до −${Math.abs(r.weight)}`}
              </span>
            </div>
            <p className="text-[11px] leading-relaxed text-[var(--tg-hint-color)]">{r.text}</p>
          </div>
        ))}
      </div>

      <Section title="Почему сравнение с медианой">
        «Много строк» не значит ничего в отрыве от того, сколько пишут остальные: у одной команды
        обычная неделя — это 200 строк, у другой 5 000. Поэтому объём кода и ревью считаются
        относительно медианы команды, а по возможности — относительно медианы своей роли, чтобы
        дизайнера не сравнивали с бэкендером. Если в роли меньше двух человек с данными, сравнение
        честно откатывается на всю команду и это подписано в разборе.
      </Section>

      <Section title="Почему есть потолки">
        Вклад выше {f.normalize_cap} медиан дальше не растёт, а один коммит засчитывается не больше
        чем в {f.max_lines_per_commit.toLocaleString("ru-RU")} строк. Без этих ограничений один
        сгенерированный файл — `package-lock.json`, миграция, вендоренная библиотека — делал бы
        автора лучшим человеком в команде.
      </Section>

      <Section title="Почему компонента может исчезнуть">
        Если у команды нет данных по компоненте, она исключается, а вес расходится по остальным.
        Обнулять нельзя: команда без пул-реквестов теряла бы вес ревью поголовно, а человек, которому
        ещё не назначили задач, — вес задач. Это уже не про его работу.
      </Section>

      <Section title="Жёлтый и красный">
        <b className="text-amber-500">Жёлтый</b> — балл ниже медианы команды на{" "}
        {f.yellow_below_median_percent}% и держится так {days(f.yellow_streak_days)} подряд, либо нет
        активности {days(f.yellow_inactive_days)} при незакрытых задачах. Это сигнал самому
        участнику.
        <br />
        <b className="text-red-500">Красный</b> — жёлтый держится ещё{" "}
        {days(f.yellow_to_red_extra_days)}, либо по какой-то задаче нет изменений{" "}
        {days(f.stuck_red_days)}. Это сигнал тимлиду.
        <br />
        Серия считается от сегодняшнего дня назад, поэтому один нормальный день обнуляет
        накопленное.
      </Section>

      <Section title="«Нет данных» — это не ноль">
        У участника без привязанного GitHub-аккаунта и без задач балла нет вообще: экран так и пишет
        «нет данных». Молчаливый ноль читался бы как «ничего не делал», а это разные вещи.
      </Section>

      <Section title="Что система не делает">
        Она не решает, хороший человек или плохой. Она показывает факты: сколько коммитов, какие
        задачи двигались, где давно ничего не менялось. Вывод — за тимлидом.
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-3 rounded-2xl bg-[var(--tg-section-bg-color)] p-3">
      <div className="mb-1 text-sm font-semibold text-[var(--tg-text-color)]">{title}</div>
      <p className="text-[11px] leading-relaxed text-[var(--tg-hint-color)]">{children}</p>
    </div>
  );
}
