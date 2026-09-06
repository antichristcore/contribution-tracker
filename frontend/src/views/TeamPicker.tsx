import { useState } from "react";
import GithubUsernameInput from "../components/GithubUsernameInput";
import { api } from "../lib/api";
import type { GithubCheck, MyTeam } from "../lib/types";
import { roleLabel } from "../lib/status";

interface Props {
  teams: MyTeam[];
  /** Логин из другого проекта — подставляем, чтобы не спрашивать дважды. */
  knownGithubUsername?: string | null;
  onPick: (teamId: number) => void;
  /** Проект создан или присоединён — открыть его сразу, без возврата к списку. */
  onEntered: (teamId: number) => void;
}

export default function TeamPicker({ teams, knownGithubUsername, onPick, onEntered }: Props) {
  const [name, setName] = useState("");
  const [repo, setRepo] = useState("");
  const [code, setCode] = useState("");
  const [githubUsername, setGithubUsername] = useState(knownGithubUsername ?? "");
  const [githubCheck, setGithubCheck] = useState<GithubCheck | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Логин обязателен в обеих формах: человек без привязки к GitHub для трекера
  // вклада не существует — его коммиты остаются ничьими.
  const githubReady = Boolean(githubCheck?.ok && githubCheck.login);

  async function createProject() {
    if (!name.trim() || !githubReady) return;
    setBusy(true);
    setError(null);
    try {
      const parts = repo.trim().replace(/^\/|\/$/g, "").split("/");
      const [github_owner, github_repo] = parts.length === 2 ? parts : [undefined, undefined];
      const team = await api.post<{ team_id: number }>("/teams", {
        name: name.trim(),
        github_owner,
        github_repo,
        github_username: githubCheck!.login,
      });
      onEntered(team.team_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось создать проект");
    } finally {
      setBusy(false);
    }
  }

  async function joinProject() {
    if (!code.trim() || !githubReady) return;
    setBusy(true);
    setError(null);
    try {
      const team = await api.post<{ team_id: number }>("/teams/join", {
        invite_code: code.trim(),
        github_username: githubCheck!.login,
      });
      onEntered(team.team_id);
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
                {t.system_role === "teamlead" ? "Тимлид" : roleLabel(t.role_in_team)}
              </div>
            </button>
          ))}
        </div>
      )}

      <div className="mb-4 rounded-2xl bg-[var(--tg-section-bg-color)] p-4">
        <div className="mb-1 text-sm font-semibold text-[var(--tg-text-color)]">Твой GitHub</div>
        <div className="mb-2 text-[11px] leading-snug text-[var(--tg-hint-color)]">
          Нужен и чтобы создать проект, и чтобы вступить в чужой. Без него приложение не поймёт,
          какие коммиты твои.
        </div>
        <GithubUsernameInput
          value={githubUsername}
          onChange={setGithubUsername}
          onCheck={setGithubCheck}
        />
      </div>

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
          disabled={busy || !githubReady || !name.trim()}
          className="w-full rounded-xl bg-[var(--tg-button-color)] py-2.5 font-medium text-[var(--tg-button-text-color)] disabled:opacity-40"
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
        <button
          onClick={joinProject}
          disabled={busy || !githubReady || !code.trim()}
          className="w-full rounded-xl bg-[var(--tg-secondary-bg-color)] py-2.5 font-medium text-[var(--tg-text-color)] disabled:opacity-40"
        >
          Вступить в команду
        </button>
      </div>

      {error && <div className="mt-3 text-sm text-red-500">{error}</div>}
    </div>
  );
}
