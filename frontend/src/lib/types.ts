export type SystemRole = "teamlead" | "member";
export type TaskStatus = "todo" | "in_progress" | "done";
export type StatusColor = "green" | "yellow" | "red" | "no_data";

export interface GithubMapping {
  github_username: string | null;
  git_author_email: string | null;
  git_author_name: string | null;
}

export interface Member {
  id: number;
  display_name: string;
  role_in_team: string;
  system_role: SystemRole;
  telegram_username: string | null;
  is_active: boolean;
  github_mapping: GithubMapping | null;
}

export interface MemberSummary extends Member {
  status_color: StatusColor;
  contribution_score: number | null;
  has_data: boolean;
}

export interface Task {
  id: number;
  title: string;
  description: string | null;
  assignee_member_id: number | null;
  created_by_member_id: number | null;
  status: TaskStatus;
  deadline_at: string | null;
  status_changed_at: string;
  completed_at: string | null;
  created_at: string;
  stuck_days: number;
  linked_commits_count: number;
  assignee_name: string | null;
}

export interface ScoreHistoryPoint {
  computed_at: string;
  contribution_score: number | null;
  commits_count_7d: number;
  commits_lines_changed_7d: number;
  tasks_assigned: number;
  tasks_completed_on_time: number;
  tasks_status_stuck_days_max: number;
  pr_review_comments_given: number;
  last_activity_days_ago: number | null;
  status_color: StatusColor;
  has_data: boolean;
}

export interface Diagnosis {
  label: string;
  explanation: string;
}

export interface PeerBasis {
  peer_basis: "role" | "team" | null;
  role_peer_count: number;
}

export interface Bootstrap {
  teams: MyTeam[];
  team_id: number | null;
  member: Member | null;
  tasks: Task[] | null;
}

export interface CommitInfo {
  id: number;
  sha: string;
  message: string | null;
  authored_at: string;
  additions: number | null;
  deletions: number | null;
  author_name: string | null;
  html_url: string | null;
}

export interface TaskHistoryEntry {
  old_status: TaskStatus | null;
  new_status: TaskStatus;
  changed_at: string;
  changed_by_name: string | null;
}

export interface TaskDetailData {
  task: Task;
  commits: CommitInfo[];
  history: TaskHistoryEntry[];
}

export interface MemberDetail {
  member: Member;
  latest: ScoreHistoryPoint | null;
  history: ScoreHistoryPoint[];
  diagnosis: Diagnosis | null;
  tasks: Task[];
  commits: CommitInfo[];
  peer_basis: "role" | "team" | null;
  role_peer_count: number;
}

export interface TeamSummaryMember {
  member_id: number;
  display_name: string;
  status_color: StatusColor;
  contribution_score: number | null;
}

export interface TeamSummary {
  median_score: number | null;
  green_count: number;
  yellow_count: number;
  red_count: number;
  no_data_count: number;
  members: TeamSummaryMember[];
}

export interface MyTeam {
  team_id: number;
  name: string;
  role_in_team: string;
  system_role: SystemRole;
}

export interface InviteInfo {
  invite_code: string;
  bot_username: string | null;
  deep_link: string | null;
}

export interface DiscoveredRepo {
  owner: string;
  repo: string;
  private: boolean;
  full_name: string;
}

export interface DiscoverResponse {
  repos: DiscoveredRepo[];
  error: string | null;
}

export interface TeamSettings {
  team_id: number;
  name: string;
  github_owner: string | null;
  github_repo: string | null;
  has_github_token: boolean;
}

export interface BeforeAfterData {
  days: string[];
  team_median_by_day: { date: string; median: number | null }[];
  members: { member_id: number; display_name: string; series: { date: string; score: number | null }[] }[];
  notifications: { member_id: number; type: string; sent_at: string; payload_summary: string | null }[];
}
