"use client";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { InviteModal } from "@/components/employer";
import { ExplanationView, FspBlock, LevelScale, MatchScore, SkillList } from "@/components/domain";
import { Button, Chip, ErrorNote, Loading, Panel, StatusChip, useToast } from "@/components/ui";
import { dateRu, daysAgo, rubRange, useApi } from "@/lib/api";
import { useDict } from "@/lib/session";
import type { CandidateCard, Need } from "@/lib/types";

function Card() {
  const { id } = useParams<{ id: string }>();
  const needId = useSearchParams().get("need");
  const { data: c, error, mutate } = useApi<CandidateCard>(`/employer/candidates/${id}${needId ? `?need_id=${needId}` : ""}`);
  const { data: need } = useApi<Need>(needId ? `/employer/needs/${needId}` : null);
  const { data: comp } = useApi<any>("/employer/company");
  const { formatName } = useDict();
  const [inviting, setInviting] = useState(false);
  const toast = useToast();
  if (error) return <ErrorNote error={error} />;
  if (!c) return <Loading />;
  return (
    <>
      {toast.node}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold sm:text-[28px]">{c.name}</h1>
          <div className="mt-1 text-[15px] text-ink/65">
            {[c.city, c.years_experience ? `опыт ${c.years_experience} г.` : null, c.work_formats.map(formatName).join(", ").toLowerCase(),
              c.salary_from ? `ожидает ${rubRange(c.salary_from, c.salary_to)}` : null].filter(Boolean).join("; ")}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {c.score !== undefined && <MatchScore score={c.score} />}
          {!c.contacts_unlocked && <Button onClick={() => setInviting(true)}>Пригласить</Button>}
        </div>
      </div>

      {c.contacts && (
        <Panel className="mb-6 border-ok/40 bg-emerald-50/40" title="Контакты открыты">
          <div className="grid gap-3 text-[15px] sm:grid-cols-4">
            <div><div className="text-xs text-ink/55">ФИО</div><b>{c.contacts.full_name}</b></div>
            <div><div className="text-xs text-ink/55">Email</div><b>{c.contacts.email || "—"}</b></div>
            <div><div className="text-xs text-ink/55">Телефон</div><b>{c.contacts.phone || "—"}</b></div>
            <div><div className="text-xs text-ink/55">Telegram</div><b>{c.contacts.telegram || "—"}</b></div>
          </div>
        </Panel>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Panel>
          <div className="text-sm text-ink/55">Категория по результатам теста</div>
          <div className="mt-1 text-[22px] font-extrabold text-plum">{c.category.specialization_name}, {c.category.grade_name}</div>
          <LevelScale theta={c.theta} current={c.category.grade} label="Кандидат" compact />
          <p className="mt-3 text-sm text-ink/60">
            Профиль подтверждён {daysAgo(c.last_activity_at)}. Категорию нельзя «нарисовать» в резюме: её выставляет адаптивный тест с уникальными заданиями.
          </p>
        </Panel>
        {c.explanation ? (
          <Panel title={need ? `Соответствие подборке «${need.title}»` : "Соответствие"}><ExplanationView e={c.explanation} compact /></Panel>
        ) : (
          <Panel title="Достижения ФСП"><FspBlock fsp={c.fsp} compact /></Panel>
        )}
      </div>

      <Panel title="Навыки, подтверждённые тестом" className="mt-6">
        <p className="mb-3 text-sm text-ink/60">Нажмите «Доказательства», чтобы увидеть конкретные задания, которые решал кандидат, и его ответы.</p>
        <SkillList skills={c.skills} candidateId={c.id} />
        {(() => {
          const claimed = (c.claimed_skills || []).filter((s) => !c.skills.some((x) => x.slug === s.slug));
          return claimed.length > 0 ? (
            <div className="mt-2 text-sm"><span className="text-ink/55">Заявлено в резюме, тестом не проверялось: </span>{claimed.map((s) => s.name).join(", ")}</div>
          ) : null;
        })()}
      </Panel>

      {c.explanation && <Panel title="Из чего сложилась оценка" className="mt-6"><ExplanationView e={c.explanation} /></Panel>}

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Panel title="Достижения ФСП"><FspBlock fsp={c.fsp} /></Panel>
        <Panel title="Опыт и о себе">
          {c.about && <p className="text-[15px] leading-relaxed">{c.about}</p>}
          {c.experience?.map((e, i) => (
            <div key={i} className="mt-3 text-sm"><b>{e.position}</b>, {e.company}, {e.period}<div className="text-ink/60">{e.description}</div></div>
          ))}
          {c.soft_skills && c.soft_skills.length > 0 && <div className="mt-4 flex flex-wrap gap-1.5">{c.soft_skills.map((s) => <Chip key={s} tone="mist">{s}</Chip>)}</div>}
          {c.tests && c.tests.length > 0 && (
            <div className="mt-5">
              <div className="mb-1 text-sm font-semibold text-plum">Тесты</div>
              {c.tests.map((t) => (
                <div key={t.id} className="flex flex-wrap items-center gap-2 py-1 text-sm">
                  <span>На {t.target_grade_name}</span><StatusChip status={t.outcome} /><span className="text-ink/55">{t.n_items} заданий, {dateRu(t.finished_at)}</span>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>
      {inviting && (
        <InviteModal open candidate={c} need={need} defaultContact={comp ? [comp.contact_telegram, comp.contact_email].filter(Boolean).join(", ") : ""}
                     onClose={() => setInviting(false)} onSent={() => { setInviting(false); toast.show("Приглашение отправлено"); mutate(); }} />
      )}
    </>
  );
}

export default function Page() {
  return <Suspense><Card /></Suspense>;
}
