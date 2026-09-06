import { Suspense, lazy, useEffect, useState } from "react";
import CommitCard from "../components/CommitCard";
import TaskRow from "../components/TaskRow";
import { api } from "../lib/api";
import { formatScore, roleLabel } from "../lib/status";
import { haptic } from "../lib/telegram";
import type { Member, MemberDetail as MemberDetailData } from "../lib/types";

// Recharts is ~5x the size of the rest of the app. Keeping it out of the main
// bundle is what makes the board open fast over a slow tunnel.
const ScoreChart = lazy(() => import("../components/ScoreChart"));

interface Props {
  memberId: number;
  currentMember: Member;
  onBack: () => void;
  onDeleted: () => void;
  onOpenTask: (taskId: number) => void;
}

export default function MemberDetail({ memberId, currentMember, onBack, onDeleted, onOpenTask }: Props) {
  const [data, setData] = useState<MemberDetailData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [githubInput, setGithubInput] = useState("");
  const [savingGithub, setSavingGithub] = useState(false);

  useEffect(() => {
    api
      .get<MemberDetailData>(`/members/${memberId}`)
      .then((d) => {
        setData(d);
        setGithubInput(d.member.github_mapping?.github_username ?? "");
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Не удалось загрузить участника"));
  }, [memberId]);

  const isOwnProfile = currentMember.id === memberId;
  const canDelete = currentMember.system_role === "teamlead" || isOwnProfile;
  const canEditGithub = currentMember.system_role === "teamlead" || currentMember.id === memberId;

  async function saveGithub() {
    setSavingGithub(true);
    try {
      await api.patch(`/members/${memberId}`, { github_username: githubInput.trim().replace(/^@/, "") || null });
      haptic("success");
    } catch (e) {
      alert(e instanceof Error ? e.message : "Не удалось сохранить GitHub username");
    } finally {
      setSavingGithub(false);
    }
  }

  async function handleDelete() {
    const who = isOwnProfile ? "свои метрики" : `все метрики участника «${data?.member.display_name}»`;
    if (!confirm(`Удалить ${who}? Действие необратимо.`)) return;
    setDeleting(true);
    try {
      await api.delete(`/members/${memberId}/profile`);
      haptic("success");
      onDeleted();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Не удалось удалить профиль");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="p-4 pb-10">
      <button onClick={onBack} className="mb-4 text-sm text-[var(--tg-link-color)]">
        ← Назад
      </button>

      {error && <div className="text-sm text-red-500">{error}</div>}
      {!data && !error && <div className="text-center text-[var(--tg-hint-color)]">Загрузка...</div>}

      {data && (
        <>
          <h1 className="mb-1 text-xl font-bold text-[var(--tg-text-color)]">{data.member.display_name}</h1>
          <div className="mb-4 text-sm text-[var(--tg-hint-color)]">{roleLabel(data.member.role_in_team)}</div>

          <div className="mb-4 grid grid-cols-2 gap-2">
            <MetricTile label="Score" value={formatScore(data.latest?.contribution_score ?? null)} />
            <MetricTile
              label="Коммиты / 7д"
              value={data.latest ? String(data.latest.commits_count_7d) : "—"}
            />
            <MetricTile
              label="Задачи в срок"
              value={
                data.latest ? `${data.latest.tasks_completed_on_time}/${data.latest.tasks_assigned}` : "—"
              }
            />
            <MetricTile
              label="Активность"
              value={
                data.latest?.last_activity_days_ago != null
                  ? `${data.latest.last_activity_days_ago} дн. назад`
                  : "—"
              }
            />
          </div>

          <div className="mb-4 rounded-2xl bg-[var(--tg-section-bg-color)] p-3">
            <div className="mb-2 text-sm font-semibold text-[var(--tg-text-color)]">GitHub</div>
            {canEditGithub ? (
              <div className="flex gap-2">
                <input
                  className="flex-1 rounded-xl bg-[var(--tg-secondary-bg-color)] px-3 py-2 text-sm text-[var(--tg-text-color)] outline-none"
                  placeholder="username"
                  value={githubInput}
                  onChange={(e) => setGithubInput(e.target.value)}
                />
                <button
                  onClick={saveGithub}
                  disabled={savingGithub}
                  className="rounded-xl bg-[var(--tg-button-color)] px-4 py-2 text-sm font-medium text-[var(--tg-button-text-color)] disabled:opacity-60"
                >
                  {savingGithub ? "..." : "Сохранить"}
                </button>
              </div>
            ) : (
              <div className="text-sm text-[var(--tg-text-color)]">
                {data.member.github_mapping?.github_username ?? "не указан"}
              </div>
            )}
          </div>

          {data.diagnosis && (
            <div className="mb-4 rounded-xl bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-400">
              <div className="font-semibold">Возможный сигнал</div>
              <div>{data.diagnosis.explanation}</div>
            </div>
          )}

          <div className="mb-4 rounded-2xl bg-[var(--tg-section-bg-color)] p-3">
            <div className="mb-1 text-sm font-semibold text-[var(--tg-text-color)]">Score за 3 недели</div>
            <div className="mb-2 text-[11px] text-[var(--tg-hint-color)]">
              {data.peer_basis === "role"
                ? `Сравнение внутри роли «${roleLabel(data.member.role_in_team)}» (${data.role_peer_count} чел.)`
                : `Сравнение по всей команде — в роли «${roleLabel(data.member.role_in_team)}» ${
                    data.role_peer_count === 1 ? "только один человек" : "не с кем сравнивать"
                  }`}
            </div>
            <Suspense fallback={<ChartSkeleton />}>
              <ScoreChart history={data.history} />
            </Suspense>
          </div>

          <div className="mb-2 text-sm font-semibold text-[var(--tg-text-color)]">Коммиты</div>
          {data.commits.length === 0 && (
            <div className="mb-4 text-sm text-[var(--tg-hint-color)]">
              Коммитов пока нет — либо не было активности, либо GitHub ещё не синхронизирован.
            </div>
          )}
          {data.commits.length > 0 && (
            <div className="mb-4">
              {data.commits.map((c) => (
                <CommitCard key={c.id} commit={c} />
              ))}
            </div>
          )}

          <div className="mb-2 text-sm font-semibold text-[var(--tg-text-color)]">Задачи</div>
          {data.tasks.length === 0 && (
            <div className="text-sm text-[var(--tg-hint-color)]">Задач пока нет.</div>
          )}
          {data.tasks.map((t) => (
            <TaskRow key={t.id} task={t} onOpen={() => onOpenTask(t.id)} />
          ))}

          {canDelete && (
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="mt-6 w-full rounded-xl bg-red-500/10 py-3 text-sm font-medium text-red-500 active:scale-95 transition-transform disabled:opacity-60"
            >
              {deleting ? "Удаляем..." : isOwnProfile ? "Удалить мой профиль" : "Удалить профиль"}
            </button>
          )}
        </>
      )}
    </div>
  );
}

function ChartSkeleton() {
  return (
    <div className="flex h-[180px] items-center justify-center text-xs text-[var(--tg-hint-color)]">
      Загружаем график...
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-[var(--tg-section-bg-color)] p-3">
      <div className="text-lg font-bold text-[var(--tg-text-color)]">{value}</div>
      <div className="text-[11px] text-[var(--tg-hint-color)]">{label}</div>
    </div>
  );
}
