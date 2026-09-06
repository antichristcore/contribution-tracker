import { useState } from "react";
import type { Member, Task } from "../lib/types";
import { roleLabel } from "../lib/status";

export interface TaskPayload {
  title: string;
  description?: string | null;
  assignee_member_id?: number | null;
  deadline_at?: string | null;
}

interface Props {
  members: Member[];
  task?: Task;
  onClose: () => void;
  onSave: (payload: TaskPayload) => Promise<void>;
}

function toDateInput(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toISOString().slice(0, 10);
}

export default function TaskModal({ members, task, onClose, onSave }: Props) {
  const isEdit = Boolean(task);
  const [title, setTitle] = useState(task?.title ?? "");
  const [description, setDescription] = useState(task?.description ?? "");
  const [assigneeId, setAssigneeId] = useState<number | "">(task?.assignee_member_id ?? "");
  const [deadline, setDeadline] = useState(toDateInput(task?.deadline_at));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const assignable = members.filter((m) => m.system_role === "member");

  async function submit() {
    if (!title.trim()) {
      setError("Название обязательно");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave({
        title: title.trim(),
        description: description.trim() || undefined,
        assignee_member_id: assigneeId === "" ? undefined : Number(assigneeId),
        deadline_at: deadline ? new Date(deadline).toISOString() : undefined,
      });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось сохранить задачу");
    } finally {
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
        <h2 className="mb-4 text-lg font-semibold text-[var(--tg-text-color)]">
          {isEdit ? `Задача #${task!.id}` : "Новая задача"}
        </h2>

        <input
          className="mb-3 w-full rounded-xl bg-[var(--tg-secondary-bg-color)] px-4 py-3 text-[var(--tg-text-color)] outline-none"
          placeholder="Название задачи"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <textarea
          className="mb-3 w-full rounded-xl bg-[var(--tg-secondary-bg-color)] px-4 py-3 text-[var(--tg-text-color)] outline-none"
          placeholder="Описание (необязательно)"
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <select
          className="mb-3 w-full rounded-xl bg-[var(--tg-secondary-bg-color)] px-4 py-3 text-[var(--tg-text-color)] outline-none"
          value={assigneeId}
          onChange={(e) => setAssigneeId(e.target.value === "" ? "" : Number(e.target.value))}
        >
          <option value="">Без исполнителя</option>
          {assignable.map((m) => (
            <option key={m.id} value={m.id}>
              {m.display_name} ({roleLabel(m.role_in_team)})
            </option>
          ))}
        </select>
        <input
          type="date"
          className="mb-4 w-full rounded-xl bg-[var(--tg-secondary-bg-color)] px-4 py-3 text-[var(--tg-text-color)] outline-none"
          value={deadline}
          onChange={(e) => setDeadline(e.target.value)}
        />

        {error && <div className="mb-3 text-sm text-red-500">{error}</div>}

        <button
          onClick={submit}
          disabled={saving}
          className="w-full rounded-xl bg-[var(--tg-button-color)] py-3 font-semibold text-[var(--tg-button-text-color)] disabled:opacity-60"
        >
          {saving ? "Сохраняем..." : isEdit ? "Сохранить" : "Создать задачу"}
        </button>
      </div>
    </div>
  );
}
