import { STATUS_META, formatScore } from "../lib/status";
import type { MemberSummary } from "../lib/types";

interface Props {
  member: MemberSummary;
  onClick: () => void;
}

const AVATAR_COLORS = [
  "bg-violet-500",
  "bg-sky-500",
  "bg-emerald-500",
  "bg-amber-500",
  "bg-pink-500",
  "bg-cyan-500",
];

function avatarColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

export default function MemberCard({ member, onClick }: Props) {
  const meta = STATUS_META[member.status_color];

  return (
    <button
      onClick={onClick}
      className="fade-in-up mb-2.5 flex w-full items-center gap-3 rounded-2xl bg-[var(--tg-section-bg-color)] p-3 text-left shadow-sm active:scale-[0.98] transition-transform"
    >
      <div className="relative shrink-0">
        <div
          className={`flex h-11 w-11 items-center justify-center rounded-full text-sm font-semibold text-white ${avatarColor(member.display_name)}`}
        >
          {initials(member.display_name)}
        </div>
        <span
          className={`absolute -bottom-0.5 -right-0.5 h-3.5 w-3.5 rounded-full border-2 border-[var(--tg-section-bg-color)] ${meta.dot} ${member.status_color === "red" ? "pulse-red" : ""}`}
        />
      </div>

      <div className="min-w-0 flex-1">
        <div className="truncate font-semibold text-[var(--tg-text-color)]">{member.display_name}</div>
        <div className="truncate text-xs text-[var(--tg-hint-color)]">{member.role_in_team}</div>
      </div>

      <div className="shrink-0 text-right">
        <div className={`text-xs font-semibold ${meta.text}`}>{meta.label}</div>
        <div className="text-[11px] text-[var(--tg-hint-color)]">
          {member.has_data ? formatScore(member.contribution_score) : "нет данных"}
        </div>
      </div>
    </button>
  );
}
