"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { InviteModal } from "@/components/employer";
import { FspBadge } from "@/components/domain";
import { Button, Chip, Empty, Field, Loading, MultiPick, PageHead, Tabs, Toggle, useToast } from "@/components/ui";
import { qs, rubRange, useApi } from "@/lib/api";
import { useDict } from "@/lib/session";
import type { CandidateCard } from "@/lib/types";

function Search() {
  const sp = useSearchParams();
  const { dict, skillName } = useDict();
  const [f, setF] = useState({ specialization: sp.get("specialization") || "", grade: sp.get("grade") || "", skills: [] as string[],
    min_skill_score: 50, has_fsp: sp.get("has_fsp") === "true", fsp_prize: false, sort: (sp.get("sort") === "fsp" ? "fsp" : "strength") as "strength" | "fsp",
    salary_max: "", formats: [] as string[], q: "" });
  const { data, mutate } = useApi<{ total: number; items: CandidateCard[] }>(`/employer/search${qs({ ...f, limit: 50 })}`, { keepPreviousData: true });
  const { data: comp } = useApi<any>("/employer/company");
  const [inviting, setInviting] = useState<CandidateCard | null>(null);
  const toast = useToast();
  if (!dict) return <Loading />;
  const spec = dict.specializations.find((s) => s.slug === f.specialization);
  return (
    <>
      <PageHead title="Поиск по базе" sub="Вся база кандидатов с подтверждённой категорией. Сортировка — по силе профиля: результат теста, достижения ФСП, актуальность." />
      {toast.node}
      <div className="panel mb-6 grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Специализация">
          <select className="input" value={f.specialization} onChange={(e) => setF({ ...f, specialization: e.target.value, skills: [] })}>
            <option value="">Любая</option>{dict.specializations.map((s) => <option key={s.slug} value={s.slug}>{s.name}</option>)}
          </select>
        </Field>
        <Field label="Грейд">
          <select className="input" value={f.grade} onChange={(e) => setF({ ...f, grade: e.target.value })}>
            <option value="">Любой</option>{dict.grades.map((g) => <option key={g.slug} value={g.slug}>{g.name}</option>)}
          </select>
        </Field>
        <Field label="Ожидания не выше, ₽"><input className="input" type="number" step={10000} value={f.salary_max} onChange={(e) => setF({ ...f, salary_max: e.target.value })} /></Field>
        <Field label="Слово в профиле"><input className="input" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} /></Field>
        <div className="sm:col-span-2 lg:col-span-3">
          <Field label={`Навыки, подтверждённые тестом с оценкой от ${f.min_skill_score}`}>
            <MultiPick options={(spec ? spec.core_skills : dict.skills.map((s) => s.slug)).map((s) => ({ value: s, label: skillName(s) }))}
                       value={f.skills} onChange={(v) => setF({ ...f, skills: v })} />
          </Field>
          <input type="range" min={30} max={90} step={5} value={f.min_skill_score} onChange={(e) => setF({ ...f, min_skill_score: Number(e.target.value) })}
                 className="mt-3 w-full max-w-xs accent-plum" aria-label="Минимальная оценка навыка" />
        </div>
        <div>
          <Toggle checked={f.has_fsp} onChange={(v) => setF({ ...f, has_fsp: v })} label="Есть достижения ФСП" />
          <Toggle checked={f.fsp_prize} onChange={(v) => setF({ ...f, fsp_prize: v })} label="Призёры соревнований ФСП" />
          <Field label="Формат"><MultiPick options={dict.work_formats.map((w) => ({ value: w.slug, label: w.name }))} value={f.formats} onChange={(v) => setF({ ...f, formats: v })} /></Field>
        </div>
      </div>
      {!data ? <Loading /> : data.items.length === 0 ? <Empty title="Никого не нашли" text="Ослабьте фильтры: например, снизьте минимальную оценку навыка." /> : (
        <>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-ink/60">Найдено: {data.total}</p>
            <div className="w-full max-w-sm"><Tabs value={f.sort} onChange={(v) => setF({ ...f, sort: v })}
              items={[{ value: "strength", label: "По силе профиля" }, { value: "fsp", label: "По результатам ФСП" }]} /></div>
          </div>
          <div className="space-y-3">
            {data.items.map((c) => (
              <div key={c.id} className="panel flex flex-wrap items-center gap-4 p-4 sm:p-5">
                <div className="flex h-14 w-14 shrink-0 flex-col items-center justify-center rounded-xl bg-plum-100 text-plum">
                  <span className="text-lg font-extrabold leading-none">{Math.round(c.score || 0)}</span><span className="text-[10px] font-semibold">сила</span>
                </div>
                <div className="min-w-0 flex-1">
                  <Link href={`/employer/candidates/${c.id}`} className="text-lg font-bold text-plum hover:underline">{c.name}</Link>
                  <div className="text-sm text-ink/60">{c.category.specialization_name}, {c.category.grade_name}{c.city ? `; ${c.city}` : ""}{c.salary_from ? `; ожидает ${rubRange(c.salary_from, c.salary_to)}` : ""}</div>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {c.skills.filter((s) => s.score !== null).slice(0, 4).map((s) => <Chip key={s.slug} tone="mist">{s.name} {s.score}</Chip>)}
                  </div>
                  {c.fsp?.has_history && <div className="mt-1.5"><FspBadge fsp={c.fsp} /></div>}
                </div>
                {!c.contacts_unlocked && <Button size="sm" onClick={() => setInviting(c)}>Пригласить</Button>}
              </div>
            ))}
          </div>
        </>
      )}
      {inviting && <InviteModal open candidate={inviting} defaultContact={comp ? [comp.contact_telegram, comp.contact_email].filter(Boolean).join(", ") : ""}
                                onClose={() => setInviting(null)} onSent={() => { setInviting(null); toast.show("Приглашение отправлено"); mutate(); }} />}
    </>
  );
}

export default function Page() {
  return <Suspense><Search /></Suspense>;
}
