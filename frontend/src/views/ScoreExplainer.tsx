import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { days, num } from "../lib/words";
import type { ScoreFormula } from "../lib/types";

interface Props {
  onBack: () => void;
}

/** Экран «Как считается вклад».
 *
 *  Числа приходят с бэка (`/scores/formula`), а не забиты в текст: копия
 *  констант в вёрстке разъехалась бы с расчётом за первую же правку весов. */
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
      text: `Доля задач, сданных до дедлайна. Считаются только те, по которым срок уже наступил. Задача без дедлайна и задача со сроком в будущем не влияют ни в плюс, ни в минус. Срок сравнивается по дню: сдал в день дедлайна, значит успел.`,
    },
    {
      label: "Код",
      weight: f.weight_code,
      text: `Строки, изменённые за ${days(f.code_window_days)}, в сравнении с серединой команды. Столько же, сколько у середины, даёт половину баллов этой строки, вдвое больше середины даёт все. Один коммит засчитывается не больше чем в ${num(f.max_lines_per_commit)} строк.`,
    },
    {
      label: "Ритм",
      weight: f.weight_rhythm,
      text: `В скольких днях из ${f.rhythm_window_days} были коммиты. ${days(f.rhythm_target_days)} с коммитами дают все баллы этой строки. Отличает ровную работу от аврала в ночь перед сдачей: строк кода может выйти поровну, а работа шла по-разному.`,
    },
    {
      label: "Ревью",
      weight: f.weight_reviews,
      text: `Комментарии в чужих пул-реквестах, тоже в сравнении с серединой команды. Если команда работает без пул-реквестов, эта строка не считается совсем, а её баллы расходятся по остальным.`,
    },
    {
      label: "Задачи без движения",
      weight: -f.penalty_max,
      text: `Штраф за задачу, по которой давно ничего не менялось. Растёт постепенно и упирается в потолок на ${days(f.stuck_red_days)}.`,
    },
  ];

  return (
    <div className="p-4 pb-10">
      <button onClick={onBack} className="mb-4 text-sm text-[var(--tg-link-color)]">
        ← Назад
      </button>

      <h1 className="mb-1 text-xl font-bold text-[var(--tg-text-color)]">Как считается вклад</h1>
      <p className="mb-4 text-xs leading-relaxed text-[var(--tg-hint-color)]">
        Вклад — целое число от 0 до {f.score_max}. Он складывается из четырёх строк и одного штрафа.
        Ничего из этого участник о себе не сообщает: всё берётся из истории git и доски задач.
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

      <Section title="Что такое «середина команды»">
        Это медиана: половина команды за неделю написала больше, половина меньше. Сравнивать
        приходится именно с ней, потому что «много строк» само по себе ничего не значит. У одной
        команды обычная неделя — это 200 строк, у другой 5 000.
      </Section>

      <Section title="Почему сравнивают внутри роли">
        Дизайнер и бэкендер пишут разное количество кода, и мерить их одной линейкой нечестно.
        Поэтому середина берётся по своей роли. Если в роли меньше двух человек с данными, сравнивать
        не с кем, и приложение честно переходит на всю команду. В разборе это подписано.
      </Section>

      <Section title="Почему есть потолки">
        Вклад выше {f.normalize_cap} середин дальше не растёт, а один коммит засчитывается не больше
        чем в {num(f.max_lines_per_commit)} строк. Без этих ограничений один сгенерированный файл,
        вроде package-lock.json или миграции, сделал бы своего автора первым человеком в команде.
      </Section>

      <Section title="Почему строка может не считаться">
        Если данных по строке нет у всей команды, она выключается, а её баллы расходятся по
        остальным. Обнулять нельзя: команда без пул-реквестов теряла бы баллы за ревью поголовно, а
        человек, которому ещё не назначили задач, терял бы баллы за задачи. Ни то, ни другое не про
        его работу.
      </Section>

      <Section title="Жёлтый и красный">
        <b className="text-amber-500">Жёлтый</b> загорается, когда вклад ниже середины команды на{" "}
        {f.yellow_below_median_percent}% и держится так {days(f.yellow_streak_days)} подряд, либо
        когда активности нет {days(f.yellow_inactive_days)} при незакрытых задачах. Это сигнал самому
        участнику.
        <br />
        <b className="text-red-500">Красный</b> загорается, когда жёлтый держится ещё{" "}
        {days(f.yellow_to_red_extra_days)}, либо когда по какой-то задаче ничего не менялось{" "}
        {days(f.stuck_red_days)}. Это сигнал тимлиду.
        <br />
        Серия считается от сегодняшнего дня назад, поэтому один нормальный день обнуляет
        накопленное.
      </Section>

      <Section title="«Нет данных» — это не ноль">
        У участника без привязанного GitHub-аккаунта и без задач вклада нет вообще, и приложение так
        и пишет: «нет данных». Ноль читался бы как «ничего не делал», а это разные вещи.
      </Section>

      <Section title="Что приложение не делает">
        Оно не решает, хороший человек или плохой. Оно показывает факты: сколько коммитов, какие
        задачи двигались, где давно ничего не менялось. Выводы остаются за тимлидом.
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
