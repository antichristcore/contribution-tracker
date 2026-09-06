import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { getTeamId } from "../lib/api";
import type { InviteInfo } from "../lib/types";

interface Props {
  onClose: () => void;
}

export default function InviteModal({ onClose }: Props) {
  const [invite, setInvite] = useState<InviteInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<"code" | "link" | null>(null);

  useEffect(() => {
    const teamId = getTeamId();
    if (!teamId) return;
    api
      .get<InviteInfo>(`/teams/${teamId}/invite`)
      .then(setInvite)
      .catch((e) => setError(e instanceof Error ? e.message : "Не удалось получить код"));
  }, []);

  async function copy(text: string, which: "code" | "link") {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(which);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      // clipboard API may be unavailable — the text is still visible to copy manually
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40" onClick={onClose}>
      <div
        className="sheet-in max-h-[85vh] w-full max-w-md overflow-y-auto rounded-t-3xl bg-[var(--tg-bg-color)] p-5 pb-8"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto mb-4 h-1.5 w-10 rounded-full bg-[var(--tg-hint-color)] opacity-40" />
        <h2 className="mb-1 text-lg font-semibold text-[var(--tg-text-color)]">Пригласить в проект</h2>
        <p className="mb-4 text-sm text-[var(--tg-hint-color)]">
          Отправь участнику ссылку или код, и он вступит в проект через бота в один клик.
        </p>

        {error && <div className="text-sm text-red-500">{error}</div>}
        {!invite && !error && <div className="text-center text-sm text-[var(--tg-hint-color)]">Загрузка...</div>}

        {invite && (
          <>
            {invite.deep_link && (
              <button
                onClick={() => copy(invite.deep_link!, "link")}
                className="mb-3 w-full truncate rounded-xl bg-[var(--tg-secondary-bg-color)] px-4 py-3 text-left text-sm text-[var(--tg-text-color)]"
              >
                {copied === "link" ? "Скопировано!" : invite.deep_link}
              </button>
            )}
            <button
              onClick={() => copy(invite.invite_code, "code")}
              className="mb-4 w-full rounded-xl bg-[var(--tg-secondary-bg-color)] px-4 py-3 text-center text-2xl font-bold tracking-widest text-[var(--tg-text-color)]"
            >
              {copied === "code" ? "Скопировано!" : invite.invite_code}
            </button>
          </>
        )}

        <button
          onClick={onClose}
          className="w-full rounded-xl bg-[var(--tg-button-color)] py-3 font-semibold text-[var(--tg-button-text-color)]"
        >
          Готово
        </button>
      </div>
    </div>
  );
}
