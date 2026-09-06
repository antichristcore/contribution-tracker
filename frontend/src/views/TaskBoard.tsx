import { useEffect, useState } from "react";
import TaskModal, { type TaskPayload } from "../components/TaskModal";
import TaskRow from "../components/TaskRow";
import { api } from "../lib/api";
import { haptic } from "../lib/telegram";
import type { Member, Task, TaskStatus } from "../lib/types";

interface Props {
  currentMember: Member;
  /** Tasks that arrived with the bootstrap request — saves a round trip. */
  initialTasks?: Task[] | null;
  onOpenTask: (taskId: number) => void;
}

const TABS: { status: TaskStatus; label: string }[] = [
  { status: "todo", label: "К выполнению" },
  { status: "in_progress", label: "В работе" },
  { status: "done", label: "Готово" },
];

export default function TaskBoard({ currentMember, initialTasks, onOpenTask }: Props) {
  const isTeamlead = currentMember.system_role === "teamlead";
  const [tasks, setTasks] = useState<Task[] | null>(initialTasks ?? null);
  const [members, setMembers] = useState<Member[]>([]);
  const [tab, setTab] = useState<TaskStatus>("in_progress");
  const [onlyMine, setOnlyMine] = useState(!isTeamlead);
  const [refreshing, setRefreshing] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setTasks(await api.get<Task[]>("/tasks"));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось загрузить задачи");
    }
  }

  useEffect(() => {
    // Tasks usually arrive with the bootstrap request; refetching them here
    // would spend another round trip on data we already have.
    if (!initialTasks) void load();
    if (isTeamlead) {
      api.get<Member[]>("/members").then(setMembers).catch(() => setMembers([]));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isTeamlead]);

  function showToast(text: string) {
    setToast(text);
    setTimeout(() => setToast(null), 3500);
  }

  async function handleRefresh() {
    setRefreshing(true);
    haptic("light");
    try {
      const res = await api.post<{ new_commits?: number; linked_commits?: number; error?: string }>(
        "/github/refresh"
      );
      await load();
      showToast(
        res.error
          ? `GitHub: ${res.error}`
          : `Новых коммитов: ${res.new_commits ?? 0} · привязано к задачам: ${res.linked_commits ?? 0}`
      );
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Не удалось обновить");
    } finally {
      setRefreshing(false);
    }
  }

  async function createTask(payload: TaskPayload) {
    const task = await api.post<{ number: number }>("/tasks", payload);
    haptic("success");
    await load();
    showToast(`Задача #${task.number} создана — этот номер нужно упоминать в коммитах`);
  }

  if (error) return <div className="p-4 text-sm text-red-500">{error}</div>;
  if (!tasks) return <div className="p-6 text-center text-[var(--tg-hint-color)]">Загрузка...</div>;

  const visible = onlyMine ? tasks.filter((t) => t.assignee_member_id === currentMember.id) : tasks;
  const byStatus = (s: TaskStatus) => visible.filter((t) => t.status === s);
  const current = byStatus(tab).sort((a, b) =>
    tab === "done"
      ? new Date(b.completed_at ?? b.status_changed_at).getTime() -
        new Date(a.completed_at ?? a.status_changed_at).getTime()
      : new Date(a.status_changed_at).getTime() - new Date(b.status_changed_at).getTime()
  );

  return (
    <div className="p-4 pb-24">
      <div className="mb-3 flex items-center justify-between">
        <h1 className="text-lg font-bold text-[var(--tg-text-color)]">Задачи</h1>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="flex items-center gap-1.5 rounded-full bg-[var(--tg-secondary-bg-color)] px-3 py-1.5 text-xs font-medium text-[var(--tg-text-color)] active:scale-95 transition-transform disabled:opacity-60"
        >
          <span className={refreshing ? "inline-block spin" : ""}>⟳</span>
          {refreshing ? "Обновляем..." : "Обновить"}
        </button>
      </div>

      <div className="mb-3 flex rounded-xl bg-[var(--tg-secondary-bg-color)] p-1">
        {TABS.map((t) => (
          <button
            key={t.status}
            onClick={() => setTab(t.status)}
            className={`flex-1 rounded-lg py-2 text-xs font-medium transition-colors ${
              tab === t.status
                ? "bg-[var(--tg-bg-color)] text-[var(--tg-text-color)] shadow-sm"
                : "text-[var(--tg-hint-color)]"
            }`}
          >
            {t.label}
            <span className="ml-1 opacity-70">{byStatus(t.status).length}</span>
          </button>
        ))}
      </div>

      <button
        onClick={() => setOnlyMine((v) => !v)}
        className={`mb-3 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
          onlyMine
            ? "bg-[var(--tg-button-color)] text-[var(--tg-button-text-color)]"
            : "bg-[var(--tg-secondary-bg-color)] text-[var(--tg-hint-color)]"
        }`}
      >
        {onlyMine ? "✓ только мои" : "только мои"}
      </button>

      {current.length === 0 ? (
        <div className="rounded-2xl bg-[var(--tg-section-bg-color)] p-6 text-center text-sm text-[var(--tg-hint-color)]">
          {onlyMine ? "Здесь пока нет твоих задач." : "В этой колонке пока пусто."}
        </div>
      ) : (
        current.map((t) => (
          <TaskRow
            key={t.id}
            task={t}
            mine={t.assignee_member_id === currentMember.id}
            onOpen={() => onOpenTask(t.id)}
          />
        ))
      )}

      {isTeamlead && (
        <button
          onClick={() => setShowCreate(true)}
          className="fixed bottom-20 right-6 flex h-14 w-14 items-center justify-center rounded-full bg-[var(--tg-button-color)] text-2xl text-[var(--tg-button-text-color)] shadow-lg active:scale-90 transition-transform"
          aria-label="Новая задача"
        >
          +
        </button>
      )}

      {showCreate && (
        <TaskModal members={members} onClose={() => setShowCreate(false)} onSave={createTask} />
      )}

      {toast && (
        <div className="fixed bottom-24 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-black/80 px-4 py-2 text-sm text-white fade-in-up">
          {toast}
        </div>
      )}
    </div>
  );
}
