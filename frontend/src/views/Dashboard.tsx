import { useEffect, useState } from "react";
import InviteModal from "../components/InviteModal";
import MemberCard from "../components/MemberCard";
import CommitHeatmap from "../components/CommitHeatmap";
import TeamPulse from "../components/TeamPulse";
import TeamSettingsModal from "../components/TeamSettingsModal";
import { api } from "../lib/api";
import { haptic } from "../lib/telegram";
import type { MemberSummary, TeamSummary } from "../lib/types";

interface Props {
  onOpenMember: (id: number) => void;
  onOpenBeforeAfter: () => void;
  onExplainScore: () => void;
}

export default function Dashboard({ onOpenMember, onOpenBeforeAfter, onExplainScore }: Props) {
  const [members, setMembers] = useState<MemberSummary[] | null>(null);
  const [summary, setSummary] = useState<TeamSummary | null>(null);
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [m, s] = await Promise.all([
        api.get<MemberSummary[]>("/members"),
        api.get<TeamSummary>("/scores/team-summary"),
      ]);
      setMembers(m);
      setSummary(s);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось загрузить данные");
    }
  }

  useEffect(() => {
    load();
  }, []);

  function showToast(text: string) {
    setToast(text);
    setTimeout(() => setToast(null), 3500);
  }

  async function handleRefresh() {
    setRefreshing(true);
    haptic("light");
    try {
      const syncRes = await api.post<{ new_commits?: number; error?: string }>("/github/refresh");
      await load();
      setLastUpdated(new Date());
      showToast(
        syncRes.error ? `GitHub: ${syncRes.error}` : `Обновлено · новых коммитов: ${syncRes.new_commits ?? 0}`
      );
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Не удалось обновить");
    } finally {
      setRefreshing(false);
    }
  }

  if (error) {
    return <div className="p-4 text-sm text-red-500">{error}</div>;
  }

  if (!members || !summary) {
    return <div className="p-6 text-center text-[var(--tg-hint-color)]">Загрузка...</div>;
  }

  // Тимлида показываем тоже — он такой же участник и тоже коммитит. Наверх,
  // чтобы список читался сверху вниз по роли, а не вперемешку.
  const teamMembers = [...members].sort(
    (a, b) => Number(b.system_role === "teamlead") - Number(a.system_role === "teamlead")
  );

  return (
    <div className="p-4 pb-24">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-bold text-[var(--tg-text-color)]">Команда</h1>
        <div className="flex gap-1.5">
          <IconButton label="Пригласить" onClick={() => setShowInviteModal(true)}>
            👥
          </IconButton>
          <IconButton label="Настройки" onClick={() => setShowSettingsModal(true)}>
            ⚙️
          </IconButton>
        </div>
      </div>

      <TeamPulse summary={summary} onExplain={onExplainScore} />

      <div className="mb-4 rounded-2xl bg-[var(--tg-section-bg-color)] p-3">
        <div className="mb-2 text-sm font-semibold text-[var(--tg-text-color)]">Активность команды</div>
        <CommitHeatmap />
      </div>

      <div className="mb-5 flex items-center justify-between">
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="flex items-center gap-2 rounded-full bg-[var(--tg-button-color)] px-4 py-2 text-sm font-medium text-[var(--tg-button-text-color)] active:scale-95 transition-transform disabled:opacity-60"
        >
          <span className={refreshing ? "inline-block spin" : ""}>⟳</span>
          {refreshing ? "Обновляем..." : "Обновить"}
        </button>
        <div className="text-right text-[11px] text-[var(--tg-hint-color)]">
          {lastUpdated && <div>Обновлено {lastUpdated.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</div>}
          <button onClick={onOpenBeforeAfter} className="text-[var(--tg-link-color)]">
            📈 Динамика
          </button>
        </div>
      </div>

      {/* Подсказка про приглашение нужна и теперь, когда в списке всегда есть
          хотя бы карточка самого тимлида: без неё одинокий проект выглядит
          законченным, а звать людей — главное первое действие. */}
      {teamMembers.filter((m) => m.system_role !== "teamlead").length === 0 && (
        <div className="mb-3 rounded-2xl bg-[var(--tg-section-bg-color)] p-6 text-center text-sm text-[var(--tg-hint-color)]">
          В команде пока только ты. Нажми «Пригласить», чтобы позвать участников.
        </div>
      )}
      {teamMembers.map((m) => (
        <MemberCard key={m.id} member={m} onClick={() => onOpenMember(m.id)} />
      ))}

      {showInviteModal && <InviteModal onClose={() => setShowInviteModal(false)} />}

      {showSettingsModal && (
        <TeamSettingsModal onClose={() => setShowSettingsModal(false)} onSaved={() => showToast("Сохранено")} />
      )}

      {toast && (
        <div className="fixed bottom-24 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-black/80 px-4 py-2 text-sm text-white fade-in-up">
          {toast}
        </div>
      )}
    </div>
  );
}

function IconButton({ children, label, onClick }: { children: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--tg-section-bg-color)] text-base active:scale-90 transition-transform"
    >
      {children}
    </button>
  );
}
