import { TASK_STATUS_META } from "../lib/status";
import type { Task } from "../lib/types";

interface Props {
  task: Task;
  mine?: boolean;
  onOpen: () => void;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

export default function TaskRow({ task, mine, onOpen }: Props) {
  const meta = TASK_STATUS_META[task.status];
  const deadline = task.deadline_at ? new Date(task.deadline_at) : null;
  const overdue = deadline && task.status !== "done" && deadline.getTime() < Date.now();
  const isStale = task.status !== "done" && task.stuck_days >= 3;

  return (
    <button
      onClick={onOpen}
      className={`fade-in-up mb-2 block w-full rounded-xl bg-[var(--tg-section-bg-color)] p-3 text-left active:scale-[0.99] transition-transform ${
        mine ? "ring-1 ring-[var(--tg-button-color)]/40" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-medium text-[var(--tg-text-color)]">
            <span className="mr-1.5 font-mono text-xs text-[var(--tg-hint-color)]">#{task.id}</span>
            {task.title}
          </div>
          <div className="mt-1 flex items-center gap-1.5 text-xs text-[var(--tg-hint-color)]">
            {task.assignee_name ? (
              <>
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-[var(--tg-secondary-bg-color)] text-[8px] font-semibold">
                  {initials(task.assignee_name)}
                </span>
                <span className="truncate">{task.assignee_name}</span>
              </>
            ) : (
              <span>без исполнителя</span>
            )}
          </div>
        </div>
        <span className={`shrink-0 rounded-full px-2 py-1 text-xs font-medium ${meta.className}`}>{meta.label}</span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--tg-hint-color)]">
        <span className={task.linked_commits_count > 0 ? "text-[var(--tg-text-color)]" : ""}>
          {task.linked_commits_count > 0 ? `🔗 ${task.linked_commits_count} комм.` : "🔗 нет коммитов"}
        </span>
        {deadline && (
          <span className={overdue ? "font-semibold text-red-500" : ""}>
            {deadline.toLocaleDateString("ru-RU")}
          </span>
        )}
        {isStale && <span className="font-semibold text-amber-500">⚠ {task.stuck_days} дн. без изменений</span>}
      </div>
    </button>
  );
}
