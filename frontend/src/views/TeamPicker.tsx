import { useState } from "react";
import { api } from "../lib/api";
import type { MyTeam } from "../lib/types";

interface Props {
  teams: MyTeam[];
  onPick: (teamId: number) => void;
  onJoined: () => void;
}

export default function TeamPicker({ teams, onPick, onJoined }: Props) {
  const [name, setName] = useState("");
  const [repo, setRepo] = useState("");
  const [code, setCode] = useState("");
  const [githubUsername, setGithubUsername] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function createProject() {
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const parts = repo.trim().replace(/^\/|\/$/g, "").split("/");
      const [github_owner, github_repo] = parts.length === 2 ? parts : [undefined, undefined];
      await api.post("/teams", { name: name.trim(), github_owner, github_repo });
      onJoined();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось создать проект");
    } finally {
      setBusy(false);
    }
  }

  async function joinProject() {
    if (!code.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/teams/join", {
        invite_code: code.trim(),
        github_username: githubUsername.trim().replace(/^@/, "") || undefined,
      });
      onJoined();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Неверный код приглашения");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md p-5">
      <h1 className="mb-4 text-lg font-bold text-[var(--tg-text-color)]">Твои проекты</h1>

      {teams.length > 0 && (
        <div className="mb-6">
          {teams.map((t) => (
            <button
              key={t.team_id}
              onClick={() => onPick(t.team_id)}
              className="mb-2 w-full rounded-xl bg-[var(--tg-section-bg-color)] p-4 text-left active:scale-[0.98] transition-transform"
            >
              <div className="font-semibold text-[var(--tg-text-color)]">{t.name}</div>
              <div className="text-xs text-[var(--tg-hint-color)]">
                {t.system_role === "teamlead" ? "Тимлид" : t.role_in_team}
              </div>
            </button>
          ))}
        </div>
      )}

      <div className="mb-4 rounded-2xl bg-[var(--tg-section-bg-color)] p-4">
        <div className="mb-2 text-sm font-semibold text-[var(--tg-text-color)]">Создать новый проект</div>
        <input
          className="mb-2 w-full rounded-xl bg-[var(--tg-secondary-bg-color)] px-3 py-2.5 text-[var(--tg-text-color)] outline-none"
          placeholder="Название проекта"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className="mb-2 w-full rounded-xl bg-[var(--tg-secondary-bg-color)] px-3 py-2.5 text-[var(--tg-text-color)] outline-none"
          placeholder="GitHub-репозиторий: owner/repo (можно позже)"
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
        />
        <button
          onClick={createProject}
          disabled={busy}
          className="w-full rounded-xl bg-[var(--tg-button-color)] py-2.5 font-medium text-[var(--tg-button-text-color)] disabled:opacity-60"
        >
          Создать (я тимлид)
        </button>
      </div>

      <div className="mb-2 rounded-2xl bg-[var(--tg-section-bg-color)] p-4">
        <div className="mb-2 text-sm font-semibold text-[var(--tg-text-color)]">Есть код приглашения?</div>
        <input
          className="mb-2 w-full rounded-xl bg-[var(--tg-secondary-bg-color)] px-3 py-2.5 uppercase text-[var(--tg-text-color)] outline-none"
          placeholder="Код от тимлида"
          value={code}
          onChange={(e) => setCode(e.target.value)}
        />
        <input
          className="mb-2 w-full rounded-xl bg-[var(--tg-secondary-bg-color)] px-3 py-2.5 text-[var(--tg-text-color)] outline-none"
          placeholder="Твой GitHub username (можно позже)"
          value={githubUsername}
          onChange={(e) => setGithubUsername(e.target.value)}
        />
        <button
          onClick={joinProject}
          disabled={busy}
          className="w-full rounded-xl bg-[var(--tg-secondary-bg-color)] py-2.5 font-medium text-[var(--tg-text-color)] disabled:opacity-60"
        >
          Вступить в команду
        </button>
      </div>

      {error && <div className="mt-3 text-sm text-red-500">{error}</div>}
    </div>
  );
}
