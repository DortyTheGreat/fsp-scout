"use client";
import clsx from "clsx";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { InviteModal, NeedDraft, NeedForm, needPayload } from "@/components/employer";
import { ExplanationView, MatchScore, SkillNames } from "@/components/domain";
import { Button, Chip, Empty, ErrorNote, Field, Loading, Modal, MultiPick, Panel, StatusChip, Tabs, Toggle, useToast } from "@/components/ui";
import { api, daysAgo, qs, results, rubRange, useApi } from "@/lib/api";
import { useDict } from "@/lib/session";
import type { CandidateCard, Need } from "@/lib/types";

type Filters = { grades: string[]; skills: string[]; has_fsp: boolean; must_full: boolean; salary_max: string; formats: string[]; include_adjacent: boolean };

function Row({ c, need, onPin, onInvite }: { c: CandidateCard; need: Need; onPin: (c: CandidateCard) => void; onInvite: (c: CandidateCard) => void }) {
  const [open, setOpen] = useState(false);
  const { formatName } = useDict();
  const e = c.explanation!;
  return (
    <div className={clsx("panel p-4 sm:p-5", c.filtered_out && "border-dashed opacity-80")}>
      <div className="flex gap-4">
        <MatchScore score={c.score || 0} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <Link href={`/employer/candidates/${c.id}?need=${need.id}`} className="text-lg font-bold text-plum hover:underline">{c.name}</Link>
            <span className="text-sm text-ink/60">{c.category.grade_name}{c.category.specialization !== need.specialization ? `, ${c.category.specialization_name}` : ""}</span>
            {c.invitation_status && <StatusChip status={c.invitation_status} />}
            {c.filtered_out && <Chip tone="warn">скрыт фильтрами, но закреплён</Chip>}
          </div>
          <div className="mt-0.5 text-sm text-ink/60">
            {[c.city, c.work_formats.map(formatName).join(", ").toLowerCase(), c.salary_from ? `ожидает ${rubRange(c.salary_from, c.salary_to)}` : null,
              c.last_activity_at ? `профиль обновлён ${daysAgo(c.last_activity_at)}` : null].filter(Boolean).join("; ")}
          </div>
          <p className="mt-2 text-[15px] leading-snug">{e.summary}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {e.must_total > 0 && <Chip tone={e.must_covered === e.must_total ? "ok" : "warn"}>обязательные: {e.must_covered} из {e.must_total}</Chip>}
            {c.fsp?.has_history && <Chip tone="signal">ФСП: {results(c.fsp.total)}{c.fsp.prizes ? `, призовых ${c.fsp.prizes}` : ""}</Chip>}
            {e.cons.slice(0, 2).map((x, i) => <Chip key={i} tone="mist">{x}</Chip>)}
          </div>
          {open && <div className="mt-4 border-t border-mist pt-4"><ExplanationView e={e} /></div>}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button size="sm" variant="ghost" onClick={() => setOpen(!open)}>{open ? "Свернуть" : "Почему он здесь"}</Button>
            <Button size="sm" variant="secondary" onClick={() => onPin(c)}>{c.pinned ? "Убрать из подборки" : "Закрепить"}</Button>
            {!c.invitation_status || c.invitation_status === "declined" || c.invitation_status === "withdrawn"
              ? <Button size="sm" onClick={() => onInvite(c)}>Пригласить</Button> : null}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function NeedPage() {
  const { id } = useParams<{ id: string }>();
  const { dict, specName, gradeName, skillName, formatName } = useDict();
  const [f, setF] = useState<Filters>({ grades: [], skills: [], has_fsp: false, must_full: false, salary_max: "", formats: [], include_adjacent: false });
  const [tab, setTab] = useState<"all" | "pinned">("all");
  const [inviting, setInviting] = useState<CandidateCard | null>(null);
  const [editing, setEditing] = useState<NeedDraft | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const toast = useToast();
  const { data: comp } = useApi<any>("/employer/company");
  const { data: cats, mutate: mcats } = useApi<any[]>(`/employer/needs/${id}/categories`);
  const query = qs({ grades: f.grades, skills: f.skills, has_fsp: f.has_fsp, must_full: f.must_full, salary_max: f.salary_max,
    formats: f.formats, include_adjacent: f.include_adjacent || undefined, limit: 50 });
  const { data, mutate, isLoading } = useApi<any>(`/employer/needs/${id}/candidates${query}`, { keepPreviousData: true });
  const { data: pinned, mutate: mpin } = useApi<CandidateCard[]>(`/employer/needs/${id}/shortlist`);
  if (!data || !dict) return <Loading />;
  const need: Need = data.need;

  async function pin(c: CandidateCard) {
    if (c.pinned) await api(`/employer/needs/${id}/shortlist/${c.id}`, { method: "DELETE" });
    else await api(`/employer/needs/${id}/shortlist`, { body: { candidate_id: c.id } });
    toast.show(c.pinned ? "Убран из подборки" : "Закреплён в подборке — не потеряется при смене фильтров");
    mutate();
    mpin();
  }
  async function saveNeed() {
    try {
      await api(`/employer/needs/${id}`, { method: "PUT", body: needPayload(editing!) });
      setEditing(null);
      mutate();
      mcats();
    } catch (e) { setErr(e); }
  }

  const skillPool = [...need.must_skills, ...need.nice_skills];
  const exact = (cats || []).filter((c) => c.relation === "exact");
  const adjacent = (cats || []).filter((c) => c.relation !== "exact" && c.count > 0);
  const contact = comp ? [comp.contact_telegram, comp.contact_email].filter(Boolean).join(", ") : "";

  return (
    <>
      {toast.node}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Link href="/employer/needs" className="text-sm font-semibold text-ink/50 hover:text-plum">Подборки</Link>
          <h1 className="mt-1 text-2xl font-extrabold sm:text-[28px]">{need.title}</h1>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Chip>{specName(need.specialization)}</Chip>
            {need.grades.map((g) => <Chip key={g}>{gradeName(g)}</Chip>)}
            <Chip tone="mist">{rubRange(need.salary_from, need.salary_to)}</Chip>
            {need.work_formats.map((w) => <Chip key={w} tone="mist">{formatName(w)}</Chip>)}
          </div>
          {need.must_skills.length > 0 && <div className="mt-3 text-sm"><span className="mr-2 text-ink/55">Обязательно:</span><span className="inline-flex"><SkillNames slugs={need.must_skills} /></span></div>}
        </div>
        <Button variant="secondary" onClick={() => setEditing({ ...need, city: need.city || "" })}>Изменить требования</Button>
      </div>

      <Panel title="Подходящие категории" className="mb-6">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[...exact, ...adjacent].slice(0, 8).map((c) => (
            <div key={`${c.specialization}-${c.grade}`} className={clsx("rounded-xl border p-4", c.relation === "exact" ? "border-plum bg-plum-50" : "border-mist-300")}>
              <div className="text-sm font-bold text-plum">{c.specialization_name}, {c.grade_name}</div>
              <div className="mt-1 text-2xl font-extrabold tabular-nums text-plum">{c.count}</div>
              <div className="text-xs text-ink/60">в категории, закрывают требования: {c.matching}</div>
              <div className="mt-1 text-xs text-ink/60">медиана ожиданий: {c.salary_median ? `${Math.round(c.salary_median / 1000)} тыс. ₽` : "—"}, с ФСП: {c.with_fsp}</div>
              {c.relation !== "exact" && <div className="mt-1 text-2xs font-semibold text-lavender">{c.relation === "adjacent_grade" ? "соседний грейд" : "смежная специализация"}</div>}
            </div>
          ))}
        </div>
        {adjacent.length > 0 && (
          <Toggle checked={f.include_adjacent} onChange={(v) => setF({ ...f, include_adjacent: v })} label="Включить в выдачу смежные категории"
                  hint="Кандидаты соседнего грейда и близких специализаций — с пониженным весом" />
        )}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
        <aside className="space-y-5 lg:sticky lg:top-6 lg:self-start">
          <div className="panel space-y-5 p-5">
            <div className="font-bold text-plum">Уточнить выдачу</div>
            <Field label="Грейд"><MultiPick options={dict.grades.map((g) => ({ value: g.slug, label: g.name }))} value={f.grades} onChange={(v) => setF({ ...f, grades: v })} /></Field>
            {skillPool.length > 0 && (
              <Field label="Навык подтверждён тестом (от 50)">
                <MultiPick options={skillPool.map((s) => ({ value: s, label: skillName(s) }))} value={f.skills} onChange={(v) => setF({ ...f, skills: v })} />
              </Field>
            )}
            <Field label="Формат"><MultiPick options={dict.work_formats.map((w) => ({ value: w.slug, label: w.name }))} value={f.formats} onChange={(v) => setF({ ...f, formats: v })} /></Field>
            <Field label="Ожидания не выше, ₽"><input className="input" type="number" step={10000} value={f.salary_max} onChange={(e) => setF({ ...f, salary_max: e.target.value })} /></Field>
            <Toggle checked={f.must_full} onChange={(v) => setF({ ...f, must_full: v })} label="Все обязательные навыки подтверждены" />
            <Toggle checked={f.has_fsp} onChange={(v) => setF({ ...f, has_fsp: v })} label="Есть достижения ФСП" />
            <button className="text-sm font-semibold text-ink/55 underline" onClick={() => setF({ grades: [], skills: [], has_fsp: false, must_full: false, salary_max: "", formats: [], include_adjacent: false })}>Сбросить фильтры</button>
          </div>
          <p className="px-1 text-xs leading-relaxed text-ink/55">
            Фильтры уточняют выдачу, не удаляя подборку: закреплённые кандидаты остаются видны с пометкой, даже если не проходят фильтр.
          </p>
        </aside>

        <div>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <Tabs value={tab} onChange={setTab} items={[{ value: "all", label: `Кандидаты (${data.total})` }, { value: "pinned", label: `Закреплённые (${pinned?.length || 0})` }]} />
            <span className={clsx("text-sm text-ink/55", isLoading && "animate-pulse")}>В категории всего: {data.total_in_category}</span>
          </div>
          {tab === "all" ? (
            <div className="space-y-3">
              {data.pinned_hidden.length > 0 && (
                <div className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-warn">
                  Закреплённые кандидаты, которых скрыли фильтры: {data.pinned_hidden.length}. Они показаны в конце списка.
                </div>
              )}
              {data.items.length === 0 && data.pinned_hidden.length === 0 && (
                <Empty title="По этим фильтрам кандидатов нет" text="Ослабьте фильтры или включите смежные категории." />
              )}
              {[...data.items, ...data.pinned_hidden].map((c: CandidateCard) => (
                <Row key={c.id} c={c} need={need} onPin={pin} onInvite={setInviting} />
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              {!pinned?.length ? <Empty title="В подборке пока никого" text="Закрепляйте кандидатов кнопкой «Закрепить» — список сохранится при любых фильтрах." /> :
                pinned.map((c) => (
                  <div key={c.id} className="panel flex flex-wrap items-center gap-4 p-4">
                    <Link href={`/employer/candidates/${c.id}?need=${need.id}`} className="min-w-0 flex-1 font-bold text-plum hover:underline">{c.name}</Link>
                    <span className="text-sm text-ink/60">{c.category.label}</span>
                    <Button size="sm" onClick={() => setInviting(c)}>Пригласить</Button>
                  </div>
                ))}
            </div>
          )}
        </div>
      </div>

      {inviting && (
        <InviteModal open candidate={inviting} need={need} defaultContact={contact} onClose={() => setInviting(null)}
                     onSent={() => { setInviting(null); toast.show("Приглашение отправлено"); mutate(); }} />
      )}
      <Modal open={!!editing} onClose={() => setEditing(null)} title="Требования подборки" wide>
        {editing && (
          <>
            <NeedForm value={editing} onChange={setEditing} />
            <ErrorNote error={err} />
            <div className="mt-6 flex justify-end gap-3">
              <Button variant="ghost" onClick={() => setEditing(null)}>Отмена</Button>
              <Button onClick={saveNeed}>Сохранить и пересчитать</Button>
            </div>
          </>
        )}
      </Modal>
    </>
  );
}
