import { useCallback, useEffect, useState } from "react";
import CommitCard from "../components/CommitCard";
import DeadlineEditor from "../components/DeadlineEditor";
import LinkCommitsModal from "../components/LinkCommitsModal";
import TaskModal, { type TaskPayload } from "../components/TaskModal";
import { api } from "../lib/api";
import { TASK_STATUS_META } from "../lib/status";
import { haptic } from "../lib/telegram";
import type { Member, TaskDetailData } from "../lib/types";

interface Props {
  taskId: number;
  currentMember: Member;
  onBack: () => void;
  onDeleted: () => void;
}

export default function TaskDetail({ taskId, currentMember, onBack, onDeleted }: Props) {
  const [data, setData] = useState<TaskDetailData | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showLinkModal, setShowLinkModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeadline, setShowDeadline] = useState(false);

  const isTeamlead = currentMember.system_role === "teamlead";

  const load = useCallback(async () => {
    try {
      setData(await api.get<TaskDetailData>(`/tasks/${taskId}`));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось загрузить задачу");
    }
  }, [taskId]);

  useEffect(() => {
    void load();
    if (isTeamlead) {
      api.get<Member[]>("/members").then(setMembers).catch(() => setMembers([]));
    }
  }, [load, isTeamlead]);

  if (error) {
    return (
      <div className="p-4">
        <BackLink onBack={onBack} />
        <div className="text-sm text-red-500">{error}</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-4">
        <BackLink onBack={onBack} />
        <div className="text-center text-[var(--tg-hint-color)]">Загрузка...</div>
      </div>
    );
  }

  const { task, commits, history } = data;
  const canEdit = isTeamlead || task.assignee_member_id === currentMember.id;
  const meta = TASK_STATUS_META[task.status];
  const deadline = task.deadline_at ? new Date(task.deadline_at) : null;
  const overdue = deadline && task.status !== "done" && deadline.getTime() < Date.now();

  async function markDone() {
    setBusy(true);
    try {
      await api.patch(`/tasks/${taskId}`, { status: "done" });
      haptic("success");
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Не удалось отметить готовой");
    } finally {
      setBusy(false);
    }
  }

  async function detachCommit(commitId: number) {
    setBusy(true);
    try {
      await api.delete(`/tasks/${taskId}/commits/${commitId}`);
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Не удалось отвязать коммит");
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit(payload: TaskPayload) {
    await api.patch(`/tasks/${taskId}`, payload);
    await load();
  }

  async function rescheduleDeadline(deadlineAt: string | null) {
    // null передаётся явно — так бэк отличает «снять срок» от «поле не трогали».
    await api.patch(`/tasks/${taskId}`, { deadline_at: deadlineAt });
    await load();
  }

  async function deleteTask() {
    if (!confirm(`Удалить задачу #${task.number}? Коммиты останутся, но перестанут быть к ней привязаны.`)) return;
    setBusy(true);
    try {
      await api.delete(`/tasks/${taskId}`);
      haptic("success");
      onDeleted();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Не удалось удалить задачу");
      setBusy(false);
    }
  }

  return (
    <div className="p-4 pb-10">
      <BackLink onBack={onBack} />

      <div className="mb-1 flex items-start justify-between gap-3">
        <h1 className="text-xl font-bold text-[var(--tg-text-color)]">
          <span className="mr-2 font-mono text-sm text-[var(--tg-hint-color)]">#{task.number}</span>
          {task.title}
        </h1>
        <span className={`mt-1 shrink-0 rounded-full px-2 py-1 text-xs font-medium ${meta.className}`}>
          {meta.label}
        </span>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-[var(--tg-hint-color)]">
        <span>{task.assignee_name ?? "без исполнителя"}</span>
        {deadline && (
          <span className={overdue ? "font-semibold text-red-500" : ""}>
            дедлайн {deadline.toLocaleDateString("ru-RU")}
          </span>
        )}
        {task.status !== "done" && task.stuck_days >= 3 && (
          <span className="font-semibold text-amber-500">⚠ {task.stuck_days} дн. без изменений</span>
        )}
      </div>

      {isTeamlead && !showDeadline && (
        <button
          onClick={() => setShowDeadline(true)}
          className="mb-3 w-full rounded-xl bg-[var(--tg-secondary-bg-color)] py-2.5 text-sm font-medium text-[var(--tg-text-color)] active:scale-[0.99] transition-transform"
        >
          {deadline ? "📅 Перенести срок" : "📅 Задать срок"}
        </button>
      )}

      {showDeadline && (
        <DeadlineEditor
          deadlineAt={task.deadline_at}
          onChange={rescheduleDeadline}
          onClose={() => setShowDeadline(false)}
        />
      )}

      {task.description && (
        <p className="mb-4 whitespace-pre-wrap text-sm text-[var(--tg-text-color)]">{task.description}</p>
      )}

      <div className="mb-4 rounded-xl bg-[var(--tg-secondary-bg-color)] p-3 text-xs text-[var(--tg-hint-color)]">
        Упомяни <span className="font-mono text-[var(--tg-text-color)]">#{task.number}</span> в сообщении коммита — он
        привяжется сюда сам, а задача перейдёт «в работе». Закрыть задачу может только человек —
        кнопкой «Отметить готовой».
      </div>

      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[var(--tg-text-color)]">Коммиты по задаче ({commits.length})</h2>
        {canEdit && (
          <button
            onClick={() => setShowLinkModal(true)}
            className="rounded-lg bg-[var(--tg-secondary-bg-color)] px-3 py-1.5 text-xs font-medium text-[var(--tg-text-color)] active:scale-95 transition-transform"
          >
            + Привязать
          </button>
        )}
      </div>

      {commits.length === 0 && (
        <div className="mb-4 rounded-xl bg-[var(--tg-section-bg-color)] p-4 text-center text-sm text-[var(--tg-hint-color)]">
          Коммитов пока нет. Либо работа ещё не начиналась, либо в сообщениях не указали #{task.number} — тогда привяжи
          вручную.
        </div>
      )}

      {commits.map((c) => (
        <CommitCard
          key={c.id}
          commit={c}
          onDetach={canEdit ? () => detachCommit(c.id) : undefined}
          detachDisabled={busy}
        />
      ))}

      {history.length > 0 && (
        <>
          <h2 className="mb-2 mt-5 text-sm font-semibold text-[var(--tg-text-color)]">История</h2>
          <div className="mb-4 rounded-xl bg-[var(--tg-section-bg-color)] p-3">
            {history.map((h, i) => (
              <div key={i} className="flex justify-between gap-2 py-0.5 text-xs text-[var(--tg-hint-color)]">
                <span>
                  {h.old_status ? `${TASK_STATUS_META[h.old_status].label} → ` : "создана · "}
                  <span className="text-[var(--tg-text-color)]">{TASK_STATUS_META[h.new_status].label}</span>
                  {" · "}
                  {h.changed_by_name ?? "автоматически"}
                </span>
                <span className="shrink-0">{new Date(h.changed_at).toLocaleDateString("ru-RU")}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {canEdit && task.status !== "done" && (
        <button
          onClick={markDone}
          disabled={busy}
          className="mt-2 w-full rounded-xl bg-[var(--tg-button-color)] py-3 font-semibold text-[var(--tg-button-text-color)] disabled:opacity-60"
        >
          Отметить готовой
        </button>
      )}

      {isTeamlead && (
        <div className="mt-3 flex gap-2">
          <button
            onClick={() => setShowEditModal(true)}
            className="flex-1 rounded-xl bg-[var(--tg-secondary-bg-color)] py-3 text-sm font-medium text-[var(--tg-text-color)]"
          >
            Редактировать
          </button>
          <button
            onClick={deleteTask}
            disabled={busy}
            className="flex-1 rounded-xl bg-red-500/10 py-3 text-sm font-medium text-red-500 disabled:opacity-60"
          >
            Удалить
          </button>
        </div>
      )}

      {showLinkModal && (
        <LinkCommitsModal taskId={taskId} onClose={() => setShowLinkModal(false)} onLinked={load} />
      )}

      {showEditModal && (
        <TaskModal members={members} task={task} onClose={() => setShowEditModal(false)} onSave={saveEdit} />
      )}
    </div>
  );
}

function BackLink({ onBack }: { onBack: () => void }) {
  return (
    <button onClick={onBack} className="mb-4 text-sm text-[var(--tg-link-color)]">
      ← Назад
    </button>
  );
}
