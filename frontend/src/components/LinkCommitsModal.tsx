import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { haptic } from "../lib/telegram";
import type { CommitInfo } from "../lib/types";

interface Props {
  taskId: number;
  onClose: () => void;
  onLinked: () => void;
}

export default function LinkCommitsModal({ taskId, onClose, onLinked }: Props) {
  const [candidates, setCandidates] = useState<CommitInfo[] | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<CommitInfo[]>(`/tasks/${taskId}/link-candidates`)
      .then(setCandidates)
      .catch((e) => setError(e instanceof Error ? e.message : "Не удалось загрузить коммиты"));
  }, [taskId]);

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function save() {
    if (selected.size === 0) return;
    setSaving(true);
    setError(null);
    try {
      await api.post(`/tasks/${taskId}/commits`, { commit_ids: [...selected] });
      haptic("success");
      onLinked();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось привязать");
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40" onClick={onClose}>
      <div
        className="sheet-in max-h-[85vh] w-full max-w-md overflow-y-auto rounded-t-3xl bg-[var(--tg-bg-color)] p-5 pb-8"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto mb-4 h-1.5 w-10 rounded-full bg-[var(--tg-hint-color)] opacity-40" />
        <h2 className="mb-1 text-lg font-semibold text-[var(--tg-text-color)]">Привязать коммиты</h2>
        <p className="mb-4 text-xs text-[var(--tg-hint-color)]">
          Коммиты команды, которые пока не относятся ни к одной задаче. Отметь те, что делались по этой задаче.
        </p>

        {error && <div className="mb-3 text-sm text-red-500">{error}</div>}
        {!candidates && !error && (
          <div className="py-6 text-center text-sm text-[var(--tg-hint-color)]">Загрузка...</div>
        )}
        {candidates?.length === 0 && (
          <div className="py-6 text-center text-sm text-[var(--tg-hint-color)]">
            Свободных коммитов нет — все уже привязаны к задачам.
          </div>
        )}

        {candidates?.map((c) => {
          const isOn = selected.has(c.id);
          return (
            <button
              key={c.id}
              onClick={() => toggle(c.id)}
              className={`mb-2 flex w-full items-start gap-3 rounded-xl p-3 text-left transition-colors ${
                isOn ? "bg-[var(--tg-button-color)]/15" : "bg-[var(--tg-secondary-bg-color)]"
              }`}
            >
              <span
                className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border text-[10px] ${
                  isOn
                    ? "border-transparent bg-[var(--tg-button-color)] text-[var(--tg-button-text-color)]"
                    : "border-[var(--tg-hint-color)]"
                }`}
              >
                {isOn ? "✓" : ""}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-[var(--tg-text-color)]">
                  {c.message?.split("\n")[0] || "(без сообщения)"}
                </span>
                <span className="mt-0.5 block text-[11px] text-[var(--tg-hint-color)]">
                  {c.author_name ?? "неизвестный автор"} · {new Date(c.authored_at).toLocaleDateString("ru-RU")}
                  {(c.additions !== null || c.deletions !== null) && (
                    <>
                      {" · "}
                      <span className="text-emerald-500">+{c.additions ?? 0}</span>{" "}
                      <span className="text-red-500">−{c.deletions ?? 0}</span>
                    </>
                  )}
                </span>
              </span>
            </button>
          );
        })}

        <button
          onClick={save}
          disabled={saving || selected.size === 0}
          className="mt-2 w-full rounded-xl bg-[var(--tg-button-color)] py-3 font-semibold text-[var(--tg-button-text-color)] disabled:opacity-50"
        >
          {saving ? "Привязываем..." : `Привязать выбранные (${selected.size})`}
        </button>
      </div>
    </div>
  );
}
