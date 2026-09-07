import { useState } from "react";
import { api } from "../lib/api";
import { ROLE_OPTIONS } from "../lib/status";
import { haptic } from "../lib/telegram";
import type { Member, SystemRole } from "../lib/types";

interface Props {
  member: Member;
  isSelf: boolean;
  onSaved: (member: Member) => void;
}

/** Смена роли участника. Виден только тимлиду.
 *
 *  Рабочая роль — не косметика: от неё зависит, с кем человека сравнивают при
 *  нормализации, поэтому дизайнер, записанный бэкендером, получает несправедливо
 *  низкий вклад. Системная роль отдельно: тимлид не участвует в подсчёте вообще. */
export default function MemberRoleEditor({ member, isSelf, onSaved }: Props) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(patch: { role_in_team?: string; system_role?: SystemRole }) {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.patch<Member>(`/members/${member.id}`, patch);
      haptic("success");
      onSaved(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось сохранить роль");
    } finally {
      setSaving(false);
    }
  }

  const isTeamlead = member.system_role === "teamlead";

  return (
    <div className="mb-4 rounded-2xl bg-[var(--tg-section-bg-color)] p-3">
      <div className="mb-2 text-sm font-semibold text-[var(--tg-text-color)]">Роль в команде</div>

      <select
        className="mb-2 w-full rounded-xl bg-[var(--tg-secondary-bg-color)] px-3 py-2.5 text-sm text-[var(--tg-text-color)] outline-none"
        value={member.role_in_team}
        disabled={saving}
        onChange={(e) => void save({ role_in_team: e.target.value })}
      >
        {ROLE_OPTIONS.some((r) => r.key === member.role_in_team) ? null : (
          <option value={member.role_in_team}>{member.role_in_team}</option>
        )}
        {ROLE_OPTIONS.map((r) => (
          <option key={r.key} value={r.key}>
            {r.label}
          </option>
        ))}
      </select>
      <div className="mb-3 text-[11px] leading-snug text-[var(--tg-hint-color)]">
        По роли подбираются те, с кем сравнивать объём кода: дизайнера не меряют бэкендером.
      </div>

      <div className="mb-1 flex rounded-xl bg-[var(--tg-secondary-bg-color)] p-1">
        {(["member", "teamlead"] as SystemRole[]).map((role) => (
          <button
            key={role}
            disabled={saving || member.system_role === role}
            onClick={() => void save({ system_role: role })}
            className={`flex-1 rounded-lg py-2 text-xs font-medium transition-colors ${
              member.system_role === role
                ? "bg-[var(--tg-bg-color)] text-[var(--tg-text-color)] shadow-sm"
                : "text-[var(--tg-hint-color)]"
            }`}
          >
            {role === "teamlead" ? "Тимлид" : "Участник"}
          </button>
        ))}
      </div>
      <div className="text-[11px] leading-snug text-[var(--tg-hint-color)]">
        {isTeamlead
          ? "Тимлид видит вклад всех, приглашает людей и меняет настройки проекта. В остальном он такой же участник: балл считается, в пульсе и на графике он есть."
          : "Участник видит доску и свой собственный прогресс, но не баллы остальных."}
        {isSelf && isTeamlead && " Снять с себя тимлида можно, только назначив другого."}
      </div>

      {error && <div className="mt-2 text-xs text-red-500">{error}</div>}
    </div>
  );
}
