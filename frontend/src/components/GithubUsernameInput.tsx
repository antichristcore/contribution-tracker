import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { GithubCheck } from "../lib/types";

// Те же правила, что и на сервере: латиница, цифры и дефисы, не в начале и
// не подряд, до 39 символов. Заведомо кривой логин отсекаем на месте — и без
// сетевого запроса на каждую опечатку.
const LOGIN_RE = /^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$/;

interface Props {
  value: string;
  onChange: (value: string) => void;
  /** Результат проверки — родитель решает, можно ли сохранять. */
  onCheck: (check: GithubCheck | null) => void;
  autoFocus?: boolean;
  placeholder?: string;
}

/** Поле ввода GitHub-логина с живой проверкой.
 *
 *  Проверка нужна не для красоты: «асдф» проходит любую валидацию формата, а
 *  коммиты к нему всё равно никогда не привяжутся, и человек так и останется
 *  «нет данных», не понимая почему. Аватарка — самое понятное подтверждение,
 *  что привязался нужный аккаунт. */
export default function GithubUsernameInput({
  value,
  onChange,
  onCheck,
  autoFocus,
  placeholder = "username",
}: Props) {
  const [check, setCheck] = useState<GithubCheck | null>(null);
  const [checking, setChecking] = useState(false);
  // Ответы приходят не по порядку: медленный запрос по «ann» не должен
  // перетереть свежий результат по «anna».
  const latest = useRef(0);

  useEffect(() => {
    const login = value.trim().replace(/^@/, "");
    setCheck(null);
    onCheck(null);
    if (login.length < 1) {
      setChecking(false);
      return;
    }

    if (!LOGIN_RE.test(login)) {
      const bad: GithubCheck = {
        ok: false,
        login,
        name: null,
        avatar_url: null,
        error: "В логине GitHub бывают только латинские буквы, цифры и дефис",
        warning: null,
      };
      setChecking(false);
      setCheck(bad);
      onCheck(bad);
      return;
    }

    setChecking(true);
    const token = ++latest.current;
    const timer = setTimeout(async () => {
      try {
        const result = await api.post<GithubCheck>("/members/github-username/check", {
          github_username: login,
        });
        if (token !== latest.current) return;
        setCheck(result);
        onCheck(result);
      } catch {
        if (token !== latest.current) return;
        // Проверка не доехала — пропускаем с оговоркой. Иначе кнопка остаётся
        // серой без единого слова почему, и человек не может ни войти, ни
        // создать проект: ровно на плохой связи, то есть на защите.
        const offline: GithubCheck = {
          ok: true,
          login,
          name: null,
          avatar_url: null,
          error: null,
          warning: "Проверить не удалось. Сохраним как есть",
        };
        setCheck(offline);
        onCheck(offline);
      } finally {
        if (token === latest.current) setChecking(false);
      }
      // 700 мс, а не 450: каждая пауза в наборе — запрос к GitHub, а анонимный
      // лимит там 60 в час на весь туннель.
    }, 700);

    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <div>
      <div className="flex items-center gap-2 rounded-xl bg-[var(--tg-secondary-bg-color)] px-3 py-2.5">
        <span className="text-sm text-[var(--tg-hint-color)]">@</span>
        <input
          autoFocus={autoFocus}
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          className="min-w-0 flex-1 bg-transparent text-sm text-[var(--tg-text-color)] outline-none"
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
        {checking && <span className="shrink-0 text-xs text-[var(--tg-hint-color)]">проверяем…</span>}
        {!checking && check?.ok && !check.warning && <span className="shrink-0 text-sm">✅</span>}
        {!checking && check && !check.ok && <span className="shrink-0 text-sm">❌</span>}
      </div>

      {!checking && check?.ok && (
        <div className="mt-2 flex items-center gap-2">
          {check.avatar_url && (
            <img src={check.avatar_url} alt="" className="h-8 w-8 shrink-0 rounded-full" />
          )}
          <div className="min-w-0">
            <div className="truncate text-sm text-[var(--tg-text-color)]">
              {check.name ?? check.login}
            </div>
            <div className="truncate text-[11px] text-[var(--tg-hint-color)]">
              {check.warning ?? `github.com/${check.login}`}
            </div>
          </div>
        </div>
      )}

      {!checking && check && !check.ok && (
        <div className="mt-1.5 text-xs text-red-500">{check.error}</div>
      )}
    </div>
  );
}
