import { Suspense, lazy, useEffect, useState } from "react";
import Dashboard from "./views/Dashboard";
import MemberDetail from "./views/MemberDetail";
import TaskBoard from "./views/TaskBoard";
import TaskDetail from "./views/TaskDetail";
import TeamPicker from "./views/TeamPicker";
import { api, getTeamId, setTeamId } from "./lib/api";
import { initTelegram, isTelegram } from "./lib/telegram";
import type { Bootstrap, Member, MyTeam, Task } from "./lib/types";

// Charting pulls in recharts; it belongs to the "До/После" screen only, so it
// stays out of the bundle the board needs to start.
const BeforeAfter = lazy(() => import("./views/BeforeAfter"));

type Tab = "board" | "team";
type Overlay =
  | { type: "task"; id: number }
  | { type: "member"; id: number }
  | { type: "beforeAfter" }
  | null;

export default function App() {
  const [myTeams, setMyTeams] = useState<MyTeam[] | null>(null);
  const [member, setMember] = useState<Member | null>(null);
  const [initialTasks, setInitialTasks] = useState<Task[] | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("board");
  const [overlay, setOverlay] = useState<Overlay>(null);

  useEffect(() => {
    initTelegram();
    void authenticate();
  }, []);

  async function authenticate() {
    if (!isTelegram() && !new URLSearchParams(window.location.search).get("as")) {
      const app = window.Telegram?.WebApp;
      setAuthError(
        "Открой это приложение через Telegram-бота. Для локальной разработки в браузере добавь ?as=<member_id> к адресу.\n\n" +
          `[debug] window.Telegram: ${Boolean(window.Telegram)} · WebApp: ${Boolean(app)} · ` +
          `initData len: ${app ? app.initData.length : "n/a"} · href: ${window.location.href}`
      );
      return;
    }
    try {
      // One request instead of /me/teams -> /me -> /tasks: over a tunnel each
      // round trip costs ~400ms, and that chain was most of the startup wait.
      const hinted = rememberedTeamId();
      const boot = await api.get<Bootstrap>(`/bootstrap${hinted !== null ? `?team_id=${hinted}` : ""}`);
      setMyTeams(boot.teams);
      if (boot.team_id !== null && boot.member) {
        setTeamId(boot.team_id);
        setInitialTasks(boot.tasks);
        setMember(boot.member);
      }
    } catch (e) {
      setAuthError(e instanceof Error ? e.message : "Не удалось авторизоваться");
    }
  }

  /** Last team this device used — lets the server resolve it in the same trip. */
  function rememberedTeamId(): number | null {
    const fromUrl = new URLSearchParams(window.location.search).get("team");
    if (fromUrl) return Number(fromUrl);
    try {
      const stored = localStorage.getItem("teamId");
      if (stored) return Number(stored);
    } catch {
      // localStorage may be unavailable — the server just falls back
    }
    return null;
  }

  async function selectTeam(teamId: number) {
    setTeamId(teamId);
    const boot = await api.get<Bootstrap>(`/bootstrap?team_id=${teamId}`);
    // Список проектов тоже обновляем: у только что созданного иначе не будет
    // имени в верхней плашке.
    setMyTeams(boot.teams);
    setInitialTasks(boot.tasks);
    setMember(boot.member);
  }

  function switchTeam() {
    setTeamId(null);
    setMember(null);
    setInitialTasks(null);
    setOverlay(null);
    setTab("board");
  }

  if (authError) return <Centered>{authError}</Centered>;

  if (isTelegram() && myTeams && !member) {
    return (
      <TeamPicker
        teams={myTeams}
        onPick={(id) => void selectTeam(id)}
        onEntered={(id) => void selectTeam(id)}
      />
    );
  }

  if (!member) return <Centered>Загрузка...</Centered>;

  const isTeamlead = member.system_role === "teamlead";
  const secondTabActive =
    tab === "team" || (overlay?.type === "member" && overlay.id === member.id) || overlay?.type === "beforeAfter";

  function openSecondTab() {
    if (isTeamlead) {
      setOverlay(null);
      setTab("team");
    } else {
      setOverlay({ type: "member", id: member!.id });
    }
  }

  function openBoard() {
    setOverlay(null);
    setTab("board");
  }

  let content;
  if (overlay?.type === "task") {
    content = (
      <TaskDetail
        taskId={overlay.id}
        currentMember={member}
        onBack={() => setOverlay(null)}
        onDeleted={() => setOverlay(null)}
      />
    );
  } else if (overlay?.type === "member") {
    content = (
      <MemberDetail
        memberId={overlay.id}
        currentMember={member}
        onBack={() => setOverlay(null)}
        onDeleted={() => setOverlay(null)}
        onOpenTask={(id) => setOverlay({ type: "task", id })}
      />
    );
  } else if (overlay?.type === "beforeAfter") {
    content = <BeforeAfter onBack={() => setOverlay(null)} />;
  } else if (tab === "team") {
    content = (
      <Dashboard
        onOpenMember={(id) => setOverlay({ type: "member", id })}
        onOpenBeforeAfter={() => setOverlay({ type: "beforeAfter" })}
      />
    );
  } else {
    content = (
      <TaskBoard
        currentMember={member}
        initialTasks={initialTasks}
        onOpenTask={(id) => setOverlay({ type: "task", id })}
      />
    );
  }

  return (
    <div className="pb-16">
      {isTelegram() && (
        <button
          onClick={switchTeam}
          className="flex w-full items-center justify-between bg-[var(--tg-secondary-bg-color)] px-4 py-3 text-left active:scale-[0.99] transition-transform"
        >
          <span className="min-w-0 truncate">
            <span className="text-[11px] text-[var(--tg-hint-color)]">Проект</span>
            <div className="truncate text-sm font-semibold text-[var(--tg-text-color)]">
              {myTeams?.find((t) => t.team_id === getTeamId())?.name}
            </div>
          </span>
          <span className="ml-3 shrink-0 rounded-full bg-[var(--tg-button-color)] px-3 py-1.5 text-xs font-medium text-[var(--tg-button-text-color)]">
            Мои проекты
          </span>
        </button>
      )}

      <Suspense fallback={<Centered>Загрузка...</Centered>}>{content}</Suspense>

      <nav className="fixed bottom-0 left-0 right-0 flex border-t border-[var(--tg-secondary-bg-color)] bg-[var(--tg-bg-color)]">
        <TabButton active={!secondTabActive} onClick={openBoard} icon="📋" label="Задачи" />
        <TabButton
          active={secondTabActive}
          onClick={openSecondTab}
          icon={isTeamlead ? "👥" : "📈"}
          label={isTeamlead ? "Команда" : "Мой прогресс"}
        />
      </nav>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: string;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] transition-colors ${
        active ? "text-[var(--tg-link-color)]" : "text-[var(--tg-hint-color)]"
      }`}
    >
      <span className="text-base">{icon}</span>
      {label}
    </button>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center whitespace-pre-wrap p-8 text-center text-sm text-[var(--tg-hint-color)]">
      {children}
    </div>
  );
}
