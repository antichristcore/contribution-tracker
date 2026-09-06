import { useState } from "react";
import GithubUsernameInput from "./GithubUsernameInput";
import { api } from "../lib/api";
import { haptic } from "../lib/telegram";
import type { GithubCheck } from "../lib/types";

interface Props {
  memberId: number;
  username: string | null;
  canEdit: boolean;
  onSaved: (username: string) => void;
}

/** Привязка к GitHub в карточке участника.
 *
 *  Обычное состояние — не поле ввода, а факт: логин, замок и карандаш. Поле,
 *  которое всегда открыто, читается как «здесь ещё ничего не настроено», хотя
 *  на самом деле от этой строки зависит, засчитается ли человеку работа. */
export default function GithubUsernameField({ memberId, username, canEdit, onSaved }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(username ?? "");
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
      onSaved(check.login);
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось сохранить");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mb-4 rounded-2xl bg-[var(--tg-section-bg-color)] p-3">
      <div className="mb-2 text-sm font-semibold text-[var(--tg-text-color)]">GitHub</div>

      {!editing && (
        <div className="flex items-center gap-2">
          <div className="min-w-0 flex-1">
            {username ? (
              <div className="truncate font-mono text-sm text-[var(--tg-text-color)]">@{username}</div>
            ) : (
              <div className="text-sm text-[var(--tg-hint-color)]">не привязан</div>
            )}
            <div className="text-[11px] text-[var(--tg-hint-color)]">
              {username ? "коммиты этого аккаунта засчитываются" : "без привязки коммиты не считаются"}
            </div>
          </div>
          {username && (
            <span className="shrink-0 text-sm" title="Аккаунт привязан">
              🔒
            </span>
          )}
          {canEdit && (
            <button
              onClick={() => {
                setDraft(username ?? "");
                setEditing(true);
              }}
              aria-label={username ? "Изменить GitHub username" : "Привязать GitHub"}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--tg-secondary-bg-color)] text-sm active:scale-90 transition-transform"
            >
              ✏️
            </button>
          )}
        </div>
      )}

      {editing && (
        <>
          <GithubUsernameInput value={draft} onChange={setDraft} onCheck={setCheck} autoFocus />
          <div className="mt-2 flex gap-2">
            <button
              onClick={save}
              disabled={saving || !check?.ok}
              className="flex-1 rounded-xl bg-[var(--tg-button-color)] py-2 text-sm font-medium text-[var(--tg-button-text-color)] disabled:opacity-40"
            >
              {saving ? "..." : "Сохранить"}
            </button>
            <button
              onClick={() => {
                setEditing(false);
                setError(null);
              }}
              disabled={saving}
              className="rounded-xl bg-[var(--tg-secondary-bg-color)] px-4 py-2 text-sm text-[var(--tg-text-color)]"
            >
              Отмена
            </button>
          </div>
          {error && <div className="mt-1.5 text-xs text-red-500">{error}</div>}
        </>
      )}
    </div>
  );
}
