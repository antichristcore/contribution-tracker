import { haptic, openLink } from "../lib/telegram";
import type { CommitInfo } from "../lib/types";

interface Props {
  commit: CommitInfo;
  /** Detach control ("×"), shown only where unlinking makes sense. */
  onDetach?: () => void;
  detachDisabled?: boolean;
  /** Показывать, к какой задаче привязан коммит. Внутри самой задачи это
   *  очевидно и только шумит, а в списках активности — самое полезное. */
  showTask?: boolean;
}

/** One commit: message, author, date, diff size, short sha. Taps through to
 *  GitHub when the team has a repo connected (synthetic demo commits don't). */
export default function CommitCard({ commit, onDetach, detachDisabled, showTask }: Props) {
  const url = commit.html_url;

  function open() {
    if (!url) return;
    haptic("light");
    openLink(url);
  }

  return (
    <div
      onClick={open}
      role={url ? "link" : undefined}
      className={`mb-2 rounded-xl bg-[var(--tg-section-bg-color)] p-3 ${
        url ? "cursor-pointer active:scale-[0.99] transition-transform" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 text-sm text-[var(--tg-text-color)]">
          {commit.message?.split("\n")[0] || "(без сообщения)"}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span
            className={`font-mono text-[10px] ${
              url ? "text-[var(--tg-link-color)]" : "text-[var(--tg-hint-color)]"
            }`}
          >
            {commit.sha.slice(0, 7)}
            {url && " ↗"}
          </span>
          {onDetach && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDetach();
              }}
              disabled={detachDisabled}
              aria-label="Отвязать коммит"
              className="px-1 text-[var(--tg-hint-color)] active:scale-90 transition-transform disabled:opacity-50"
            >
              ×
            </button>
          )}
        </div>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--tg-hint-color)]">
        <span>{commit.author_name ?? "неизвестный автор"}</span>
        {showTask &&
          (commit.task_number ? (
            <span className="rounded-full bg-[var(--tg-secondary-bg-color)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--tg-text-color)]">
              #{commit.task_number}
            </span>
          ) : (
            <span className="italic">без задачи</span>
          ))}
        <span>{new Date(commit.authored_at).toLocaleDateString("ru-RU")}</span>
        {(commit.additions !== null || commit.deletions !== null) && (
          <span>
            <span className="text-emerald-500">+{commit.additions ?? 0}</span>{" "}
            <span className="text-red-500">−{commit.deletions ?? 0}</span>
          </span>
        )}
      </div>
    </div>
  );
}
