"use client";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { SkillNames } from "@/components/domain";
import { Button, ErrorNote, Field, Loading, PageHead, Panel, StatusChip } from "@/components/ui";
import { api, rubRange, useApi } from "@/lib/api";
import { useDict } from "@/lib/session";

export default function VacancyPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data: v, mutate } = useApi<any>(`/vacancies/${id}`);
  const { formatName } = useDict();
  const [letter, setLetter] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (!v) return <Loading />;

  async function apply() {
    setBusy(true);
    setErr(null);
    try { await api(`/vacancies/${id}/apply`, { body: { cover_letter: letter } }); mutate(); } catch (e) { setErr(e); } finally { setBusy(false); }
  }
  async function vacancyTest() {
    setBusy(true);
    try { const a = await api<any>("/tests/start", { body: { target_grade: v.grade === "intern" ? "junior" : v.grade, vacancy_id: v.id } }); router.push(`/candidate/test/${a.id}`); }
    catch (e) { setErr(e); setBusy(false); }
  }

  return (
    <>
      <PageHead title={v.title} sub={`${v.company.name}${v.city ? `, ${v.city}` : ""}, ${formatName(v.work_format).toLowerCase()}`} />
      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <Panel>
          <div className="text-2xl font-extrabold text-plum">{rubRange(v.salary_from, v.salary_to)}</div>
          <div className="mt-1 text-sm text-ink/60">{v.specialization_name}, {v.grade_name}</div>
          <p className="mt-5 whitespace-pre-line text-[15px] leading-relaxed">{v.description}</p>
          <div className="mt-5 space-y-3">
            {v.must_skills.length > 0 && <div><div className="mb-1.5 text-sm font-semibold">Обязательно</div><SkillNames slugs={v.must_skills} /></div>}
            {v.nice_skills.length > 0 && <div><div className="mb-1.5 text-sm font-semibold">Будет плюсом</div><SkillNames slugs={v.nice_skills} tone="mist" /></div>}
          </div>
        </Panel>
        <div className="space-y-6">
          <Panel title="Отклик">
            {v.my_application ? (
              <div className="flex items-center gap-3"><StatusChip status={v.my_application} /><span className="text-sm text-ink/60">Статус обновится, когда компания ответит.</span></div>
            ) : (
              <>
                <Field label="Сопроводительное письмо (необязательно)"><textarea className="input min-h-28" value={letter} onChange={(e) => setLetter(e.target.value)} /></Field>
                <p className="mt-2 text-xs text-ink/55">После отклика компания увидит ваши контакты и профиль.</p>
                <ErrorNote error={err} />
                <Button className="mt-4 w-full" onClick={apply} loading={busy}>Откликнуться</Button>
              </>
            )}
          </Panel>
          <Panel title="Тест под эту вакансию">
            {v.my_vacancy_test ? (
              <p className="text-sm">Пройден: <StatusChip status={v.my_vacancy_test.outcome || v.my_vacancy_test.status} /></p>
            ) : (
              <>
                <p className="text-sm text-ink/65">Необязательно. Задания собираются под стек вакансии — результат увидит работодатель вместе с откликом.</p>
                <Button variant="secondary" className="mt-4" onClick={vacancyTest} loading={busy}>Пройти тест под вакансию</Button>
              </>
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}
