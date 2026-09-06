import { Suspense, lazy, useEffect, useState } from "react";
import CommitCard from "../components/CommitCard";
import CommitHeatmap from "../components/CommitHeatmap";
import GithubUsernameField from "../components/GithubUsernameField";
import MemberRoleEditor from "../components/MemberRoleEditor";
import ScoreBreakdown from "../components/ScoreBreakdown";
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
  onExplainScore: () => void;
}

export default function MemberDetail({
  memberId,
  currentMember,
  onBack,
  onDeleted,
  onOpenTask,
  onExplainScore,
}: Props) {
  const [data, setData] = useState<MemberDetailData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    api
      .get<MemberDetailData>(`/members/${memberId}`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Не удалось загрузить участника"));
  }, [memberId]);

  const isTeamlead = currentMember.system_role === "teamlead";
  const isOwnProfile = currentMember.id === memberId;
  const canDelete = isTeamlead || isOwnProfile;
  const canEditGithub = isTeamlead || isOwnProfile;

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

          {isTeamlead && (
            <MemberRoleEditor
              member={data.member}
              isSelf={isOwnProfile}
              onSaved={(m) => setData({ ...data, member: m })}
            />
          )}

          <div className="mb-4 grid grid-cols-2 gap-2">
            {/* Разбор считается прямо сейчас, а latest — с прошлого пересчёта.
                Если плитка возьмёт latest, а разбор покажет свежее число,
                расхождение прочитается как баг. */}
            <MetricTile
              label="Вклад"
              value={formatScore(data.breakdown?.score ?? data.latest?.contribution_score ?? null)}
            />
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

          {data.breakdown && <ScoreBreakdown breakdown={data.breakdown} onExplain={onExplainScore} />}

          <GithubUsernameField
            memberId={memberId}
            username={data.member.github_mapping?.github_username ?? null}
            canEdit={canEditGithub}
            onSaved={(username) =>
              setData({
                ...data,
                member: {
                  ...data.member,
                  github_mapping: {
                    git_author_email: data.member.github_mapping?.git_author_email ?? null,
                    git_author_name: data.member.github_mapping?.git_author_name ?? null,
                    github_username: username,
                  },
                },
              })
            }
          />

          {data.diagnosis && (
            <div className="mb-4 rounded-xl bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-400">
              <div className="font-semibold">Возможный сигнал</div>
              <div>{data.diagnosis.explanation}</div>
            </div>
          )}

          <div className="mb-4 rounded-2xl bg-[var(--tg-section-bg-color)] p-3">
            <div className="mb-1 text-sm font-semibold text-[var(--tg-text-color)]">Вклад за 3 недели</div>
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

          <div className="mb-4 rounded-2xl bg-[var(--tg-section-bg-color)] p-3">
            <div className="mb-2 text-sm font-semibold text-[var(--tg-text-color)]">Активность</div>
            <CommitHeatmap memberId={memberId} />
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
                <CommitCard key={c.id} commit={c} showTask />
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
