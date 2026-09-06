import { useState } from "react";
import GithubUsernameInput from "../components/GithubUsernameInput";
import { api } from "../lib/api";
import { haptic } from "../lib/telegram";
import type { GithubCheck } from "../lib/types";

interface Props {
  memberId: number;
  /** Логин из другого проекта этого же человека. */
  knownUsername?: string | null;
  onDone: () => void;
}

/** Блокирующий экран для участника, который уже в проекте, но без привязки
 *  к GitHub.
 *
 *  Пускать его на доску бессмысленно: его коммиты остаются ничьими, вклад не
 *  считается, а сам он висит в команде как «нет данных» и не понимает почему.
 *  Это единственное место, где приложение чего-то требует до показа данных. */
export default function GithubGate({ memberId, knownUsername, onDone }: Props) {
  const [value, setValue] = useState(knownUsername ?? "");
  const [check, setCheck] = useState<GithubCheck | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    if (!check?.ok || !check.login) return;
    setSaving(true);
    setError(null);
    try {
      await api.patch(`/members/${memberId}`, { github_username: check.login });
      haptic("success");
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось сохранить");
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-md p-5">
      <h1 className="mb-1 text-xl font-bold text-[var(--tg-text-color)]">Привяжи GitHub</h1>
      <p className="mb-4 text-sm leading-relaxed text-[var(--tg-hint-color)]">
        Без этого твои коммиты остаются ничьими: задачи не двигаются, вклад не считается, а в команде
        ты выглядишь как «нет данных». Достаточно одного раза.
      </p>

      <div className="mb-3 rounded-2xl bg-[var(--tg-section-bg-color)] p-4">
        <GithubUsernameInput value={value} onChange={setValue} onCheck={setCheck} autoFocus />
        <button
          onClick={save}
          disabled={saving || !check?.ok}
          className="mt-3 w-full rounded-xl bg-[var(--tg-button-color)] py-2.5 font-medium text-[var(--tg-button-text-color)] disabled:opacity-40"
        >
          {saving ? "Сохраняем..." : "Продолжить"}
        </button>
        {error && <div className="mt-2 text-xs text-red-500">{error}</div>}
      </div>

      <p className="text-[11px] leading-relaxed text-[var(--tg-hint-color)]">
        Это тот логин, под которым ты коммитишь: он виден в адресе твоего профиля,
        github.com/<b>username</b>.
      </p>
    </div>
  );
}
