import { TASK_STATUS_META } from "../lib/status";
import { commits, days } from "../lib/words";
import type { Task } from "../lib/types";

interface Props {
  task: Task;
  mine?: boolean;
  onOpen: () => void;
  /** «✓» — закрыть задачу прямо с доски. Передаётся только тому, кто имеет
   *  на это право: коммит задачу больше не закрывает, и единственный путь
   *  к «готово» не должен быть спрятан в два тапа. */
  onComplete?: () => void;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

export default function TaskRow({ task, mine, onOpen, onComplete }: Props) {
  const meta = TASK_STATUS_META[task.status];
  const deadline = task.deadline_at ? new Date(task.deadline_at) : null;
  const overdue = deadline && task.status !== "done" && deadline.getTime() < Date.now();
  const isStale = task.status !== "done" && task.stuck_days >= 3;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onOpen();
      }}
      className={`fade-in-up mb-2 block w-full cursor-pointer rounded-xl bg-[var(--tg-section-bg-color)] p-3 text-left active:scale-[0.99] transition-transform ${
        mine ? "ring-1 ring-[var(--tg-button-color)]/40" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-medium text-[var(--tg-text-color)]">
            <span className="mr-1.5 font-mono text-xs text-[var(--tg-hint-color)]">#{task.number}</span>
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
        <div className="flex shrink-0 items-center gap-1.5">
          <span className={`rounded-full px-2 py-1 text-xs font-medium ${meta.className}`}>{meta.label}</span>
          {onComplete && task.status !== "done" && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onComplete();
              }}
              aria-label={`Закрыть задачу #${task.number}`}
              className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-500/15 text-sm text-emerald-600 active:scale-90 transition-transform"
            >
              ✓
            </button>
          )}
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--tg-hint-color)]">
        <span className={task.linked_commits_count > 0 ? "text-[var(--tg-text-color)]" : ""}>
          {task.linked_commits_count > 0 ? `🔗 ${commits(task.linked_commits_count)}` : "🔗 нет коммитов"}
        </span>
        {deadline && (
          <span className={overdue ? "font-semibold text-red-500" : ""}>
            {deadline.toLocaleDateString("ru-RU")}
          </span>
        )}
        {isStale && (
          <span className="font-semibold text-amber-500">⚠ {days(task.stuck_days)} без изменений</span>
        )}
      </div>
    </div>
  );
}
