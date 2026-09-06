import { useEffect, useState } from "react";
import { api, getTeamId, setTeamId } from "../lib/api";
import type { DiscoverResponse, DiscoveredRepo, TeamSettings } from "../lib/types";

interface Props {
  onClose: () => void;
  onSaved: () => void;
}

export default function TeamSettingsModal({ onClose, onSaved }: Props) {
  const [name, setName] = useState("");
  const [repo, setRepo] = useState("");
  const [token, setToken] = useState("");
  const [hasToken, setHasToken] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [candidates, setCandidates] = useState<DiscoveredRepo[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const teamId = getTeamId();
    if (!teamId) return;
    api
      .get<TeamSettings>(`/teams/${teamId}/settings`)
      .then((s) => {
        setName(s.name);
        setRepo(s.github_owner && s.github_repo ? `${s.github_owner}/${s.github_repo}` : "");
        setHasToken(s.has_github_token);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Не удалось загрузить настройки"))
      .finally(() => setLoading(false));
  }, []);

  async function findRepoByToken() {
    if (!token.trim()) {
      setError("Сначала вставь токен");
      return;
    }
    setDiscovering(true);
    setError(null);
    setCandidates(null);
    try {
      const res = await api.post<DiscoverResponse>("/github/discover-repos", { token: token.trim() });
      if (res.error) {
        setError(res.error);
      } else if (res.repos.length === 0) {
        setError("Токен не даёт доступа ни к одному репозиторию.");
      } else if (res.repos.length === 1) {
        setRepo(res.repos[0].full_name);
      } else {
        setCandidates(res.repos);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось проверить токен");
    } finally {
      setDiscovering(false);
    }
  }

  function pickCandidate(r: DiscoveredRepo) {
    setRepo(r.full_name);
    setCandidates(null);
  }

  async function save() {
    const teamId = getTeamId();
    if (!teamId) return;
    setSaving(true);
    setError(null);
    try {
      const parts = repo.trim().replace(/^\/|\/$/g, "").split("/");
      const [github_owner, github_repo] = parts.length === 2 ? parts : [null, null];
      const body: Record<string, unknown> = { name: name.trim(), github_owner, github_repo };
      if (token.trim()) body.github_token = token.trim();
      await api.patch(`/teams/${teamId}/settings`, body);
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось сохранить");
    } finally {
      setSaving(false);
    }
  }

  async function clearToken() {
    const teamId = getTeamId();
    if (!teamId) return;
    setSaving(true);
    try {
      await api.patch(`/teams/${teamId}/settings`, { github_token: "" });
      setHasToken(false);
      setToken("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось удалить токен");
    } finally {
      setSaving(false);
    }
  }

  async function deleteProject() {
    const teamId = getTeamId();
    if (!teamId) return;
    if (!confirm(`Удалить проект «${name}» насовсем? Все участники, задачи и история пропадут.`)) return;
    setDeleting(true);
    setError(null);
    try {
      await api.delete(`/teams/${teamId}`);
      setTeamId(null);
      window.location.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось удалить проект");
      setDeleting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40" onClick={onClose}>
      <div
        className="sheet-in max-h-[85vh] w-full max-w-md overflow-y-auto rounded-t-3xl bg-[var(--tg-bg-color)] p-5 pb-8"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto mb-4 h-1.5 w-10 rounded-full bg-[var(--tg-hint-color)] opacity-40" />
        <h2 className="mb-4 text-lg font-semibold text-[var(--tg-text-color)]">Настройки проекта</h2>

        {loading ? (
          <div className="text-center text-sm text-[var(--tg-hint-color)]">Загрузка...</div>
        ) : (
          <>
            <label className="mb-1 block text-xs text-[var(--tg-hint-color)]">Название проекта</label>
            <input
              className="mb-3 w-full rounded-xl bg-[var(--tg-secondary-bg-color)] px-4 py-3 text-[var(--tg-text-color)] outline-none"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />

            <label className="mb-1 block text-xs text-[var(--tg-hint-color)]">
              GitHub-токен (нужен только для приватного репозитория)
            </label>
            <div className="mb-1 flex gap-2">
              <input
                type="password"
                className="flex-1 rounded-xl bg-[var(--tg-secondary-bg-color)] px-4 py-3 text-[var(--tg-text-color)] outline-none"
                placeholder={hasToken ? "•••••••••••• (уже задан)" : "ghp_..."}
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
              {hasToken && (
                <button
                  onClick={clearToken}
                  disabled={saving}
                  className="rounded-xl bg-[var(--tg-secondary-bg-color)] px-3 text-sm text-[var(--tg-hint-color)]"
                >
                  Убрать
                </button>
              )}
            </div>
            <button
              onClick={findRepoByToken}
              disabled={discovering || !token.trim()}
              className="mb-3 w-full rounded-xl bg-[var(--tg-secondary-bg-color)] py-2.5 text-sm font-medium text-[var(--tg-text-color)] disabled:opacity-50"
            >
              {discovering ? "Ищем..." : "🔍 Определить репозиторий по токену"}
            </button>

            {candidates && (
              <div className="mb-3 rounded-xl bg-[var(--tg-secondary-bg-color)] p-2">
                <div className="mb-1 px-1 text-[11px] text-[var(--tg-hint-color)]">
                  Токен даёт доступ к нескольким репозиториям — выбери нужный:
                </div>
                {candidates.map((r) => (
                  <button
                    key={r.full_name}
                    onClick={() => pickCandidate(r)}
                    className="block w-full rounded-lg px-2 py-1.5 text-left text-sm text-[var(--tg-text-color)] hover:bg-[var(--tg-bg-color)]"
                  >
                    {r.full_name} {r.private && "🔒"}
                  </button>
                ))}
              </div>
            )}

            <label className="mb-1 block text-xs text-[var(--tg-hint-color)]">Репозиторий</label>
            <input
              className="mb-4 w-full rounded-xl bg-[var(--tg-secondary-bg-color)] px-4 py-3 text-[var(--tg-text-color)] outline-none"
              placeholder="owner/repo (заполнится само, или впиши вручную)"
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
            />

            {error && <div className="mb-3 text-sm text-red-500">{error}</div>}
            <button
              onClick={save}
              disabled={saving}
              className="mb-3 w-full rounded-xl bg-[var(--tg-button-color)] py-3 font-semibold text-[var(--tg-button-text-color)] disabled:opacity-60"
            >
              {saving ? "Сохраняем..." : "Сохранить"}
            </button>
            <button
              onClick={deleteProject}
              disabled={deleting}
              className="w-full rounded-xl bg-red-500/10 py-3 font-medium text-red-500 disabled:opacity-60"
            >
              {deleting ? "Удаляем..." : "Удалить проект"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
