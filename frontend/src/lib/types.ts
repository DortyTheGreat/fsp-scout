export type Role = "candidate" | "employer" | "admin";

export interface User {
  id: number;
  email: string;
  role: Role;
  is_email_verified: boolean;
  name?: string | null;
}

export interface Grade {
  slug: string;
  name: string;
  experience: string;
  cut: number | null;
  order: number;
}

export interface Dict {
  grades: Grade[];
  skills: { slug: string; name: string; group: string }[];
  specializations: { slug: string; name: string; direction: string; description: string; core_skills: string[]; stacks: string[] }[];
  industries: { slug: string; name: string }[];
  work_formats: { slug: string; name: string }[];
  roles: { slug: string; name: string }[];
  soft_skills: string[];
  decline_reasons: { slug: string; name: string; side: string }[];
}

export interface Category {
  specialization: string | null;
  specialization_name: string | null;
  grade: string | null;
  grade_name: string | null;
  label: string;
}

export interface SkillView {
  slug: string;
  name: string;
  score: number | null;
  n: number;
  n_correct?: number;
  confidence?: string;
  se?: number;
  fsp_confirmed?: boolean;
  fsp_level?: number;
  evidence?: { response_id: number; attempt_id: number; title: string; level: string; correct: boolean; difficulty: number; date: string }[];
  fsp_evidence?: { event: string; date: string; place: number; participants_total: number; level: string; role?: string }[];
}

export interface FspView {
  linked: boolean;
  hidden?: boolean;
  fsp_id?: string | null;
  has_history: boolean;
  total: number;
  prizes: number;
  sport_rank?: string | null;
  score: number;
  by_discipline: Record<string, { count: number; prizes: number; best_place: string; strength: number; name: string }>;
  best?: { event: string; result: string; level_name: string; date: string; discipline_name: string; strength: number } | null;
  max_strength?: number;
  items?: {
    id: string; event_name: string; discipline_name: string; level_name: string; date: string; place: number;
    participants_total: number; is_prize: boolean; team_name?: string; role?: string; stack?: string[];
    tasks_solved?: number; tasks_total?: number; protocol_url: string; verified: boolean;
    result?: string; strength?: number; skills?: string[];
  }[];
  fetched_at?: string;
}

export interface FspMatch {
  has_history: boolean; value: number; points: number; sport_rank?: string | null; prizes?: number; total?: number;
  items: { event: string; result: string; level?: string; date: string; discipline?: string; role?: string; relevance: number;
    points: number; matched_skills: string[] }[];
}

export interface Explanation {
  summary: string;
  pros: string[];
  cons: string[];
  factors: { key: string; name: string; value: number; weight: number; points: number }[];
  must_covered: number;
  must_total: number;
  skills: Record<string, { fit: number; source: string; score?: number; n?: number; required?: number; must: boolean }>;
  fsp?: FspMatch;
  borderline?: { to: string; p: number } | null;
  salary_multiplier?: number;
}

export interface CandidateCard {
  id: number;
  name: string;
  category: Category;
  theta: number | null;
  city?: string | null;
  years_experience?: number | null;
  work_formats: string[];
  salary_from?: number | null;
  salary_to?: number | null;
  skills: SkillView[];
  fsp: FspView;
  last_activity_at?: string | null;
  contacts_unlocked: boolean;
  contacts?: { full_name: string; email?: string; phone?: string; telegram?: string };
  score?: number;
  features?: Record<string, number>;
  explanation?: Explanation;
  pinned?: boolean;
  filtered_out?: boolean;
  invitation_status?: string | null;
  about?: string | null;
  experience?: { company: string; position: string; period: string; description?: string }[];
  claimed_skills?: { slug: string; name: string }[];
  soft_skills?: string[];
  roles?: string[];
  tests?: { id: number; target_grade: string; target_grade_name: string; outcome: string; theta: number; se: number; n_items: number; finished_at: string }[];
}

export interface Attempt {
  id: number;
  kind: string;
  specialization: string;
  target_grade: string;
  status: "in_progress" | "finished";
  outcome: "passed" | "failed" | "needs_confirmation" | null;
  theta: number;
  se: number;
  decision: {
    theta: number; se: number; cut: number; target_grade: string; passed: boolean; confident: boolean; p_pass: number;
    estimated_grade: string; n_items: number; interval: [number, number]; upgrade_suggested: string | null;
    lower_grade: string | null; can_accept_lower: boolean; grade_assigned?: string; grade_confirmed?: string; abandoned?: boolean;
    aberrant?: boolean; person_fit?: number; n_prior_items?: number;
  };
  trace: { n: number; theta: number; se: number }[];
  n_answered: number;
  max_items: number;
  min_items: number;
  started_at: string;
  finished_at: string | null;
  current?: {
    id: number; order: number; title: string; prompt: string; fmt: "single" | "multi" | "input"; code?: string | null;
    lang?: string | null; options?: string[] | null; placeholder?: string | null; time_limit_s: number; presented_at: string;
  };
  items?: { order: number; title: string; correct: boolean; time_ms: number }[];
}

export interface Invitation {
  id: number;
  title: string;
  description: string;
  salary_from: number;
  salary_to: number;
  work_format?: string | null;
  contact_method: string;
  status: "sent" | "viewed" | "accepted" | "declined" | "withdrawn";
  decline_reason?: string | null;
  decline_comment?: string | null;
  created_at: string;
  viewed_at?: string | null;
  responded_at?: string | null;
  company: { id: number; name: string; description: string; industry?: string; city?: string; website?: string; size?: string };
  candidate?: CandidateCard;
  match?: { score: number; explanation: Explanation };
  match_summary?: string;
  history?: { status: string; at: string; by: string }[];
  messages?: InvitationMessage[];
  messages_count?: number;
  salary_context?: { candidate_from?: number | null; candidate_to?: number | null; verdict: "below" | "covers" | "overlaps" | "unknown";
    text: string; category_median?: number | null };
}

export interface InvitationMessage { id: number; author_role: "candidate" | "employer"; text: string; created_at: string }

export interface Need {
  id: number;
  title: string;
  description: string;
  specialization: string;
  grades: string[];
  must_skills: string[];
  nice_skills: string[];
  work_formats: string[];
  city?: string | null;
  salary_from?: number | null;
  salary_to?: number | null;
  allow_adjacent: boolean;
  parsed_by: string;
  status: string;
  created_at: string;
}

export interface Vacancy {
  id: number;
  title: string;
  description: string;
  specialization: string;
  specialization_name: string;
  grade: string;
  grade_name: string;
  must_skills: string[];
  nice_skills: string[];
  work_format: string;
  city?: string | null;
  salary_from: number;
  salary_to: number;
  status: string;
  created_at: string;
  company: { id: number; name: string; description: string; city?: string };
  match?: { score: number; summary: string; same_category: boolean };
  my_application?: string | null;
  applications?: { total: number; new: number };
}
