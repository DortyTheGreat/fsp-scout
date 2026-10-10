"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Prompt, SkillNames } from "@/components/domain";
import { Button, Chip, Empty, Loading, Panel, StatusChip, Tabs } from "@/components/ui";
import { api, dateRu, rubRange, useApi } from "@/lib/api";
import type { Vacancy } from "@/lib/types";

function Blueprint({ id }: { id: string }) {
  const { data } = useApi<any>(`/employer/vacancies/${id}/test-blueprint`);
  if (!data) return <Loading />;
  return (
    <div className="space-y-6">
      <Panel title="Как система соберёт тест под эту вакансию">
        <p className="text-[15px] text-ink/70">
          Доли навыков в тесте следуют требованиям вакансии: обязательные весят вдвое больше желательных. Внутри навыка адаптивный алгоритм выбирает задания,
          которые точнее всего проверяют порог грейда. Пул: {data.pool_size} откалиброванных шаблонов, длина теста {data.min_items}–{data.max_items} заданий.
        </p>
        <div className="mt-4 space-y-2">
          {Object.entries<any>(data.blueprint).sort((a, b) => b[1].share - a[1].share).map(([slug, b]) => (
            <div key={slug} className="flex items-center gap-3 text-sm">
              <span className="w-56 shrink-0 font-semibold">{b.name}</span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-mist"><div className="h-full bg-plum" style={{ width: `${b.share * 100}%` }} /></div>
              <span className="w-28 text-right text-ink/60">{Math.round(b.share * 100)}%, шаблонов {b.templates}</span>
            </div>
          ))}
        </div>
        {data.uncovered_skills.length > 0 && (
          <p className="mt-4 text-sm text-warn">Для навыков {data.uncovered_skills.map((s: any) => s.name).join(", ")} в банке пока нет заданий — их можно сгенерировать LLM и отправить на калибровку в админ-панели.</p>
        )}
      </Panel>
      {data.sample && (
        <Panel title="Один шаблон — три разных кандидата">
          <p className="mb-4 text-sm text-ink/65">
            Шаблон <code className="rounded bg-mist px-1">{data.sample.template_id}</code> (трудность b = {data.sample.b.toFixed(2)}).
            Каждый кандидат получает свой экземпляр: структура решения та же, ответ — другой. Поэтому слитые ответы бесполезны, а сложность сопоставима.
          </p>
          <div className="grid gap-4 lg:grid-cols-3">
            {data.sample.instances.map((inst: any, i: number) => (
              <div key={i} className="rounded-xl border border-mist-300 p-4">
                <div className="mb-2 text-xs font-semibold text-lavender">Кандидат {i + 1}</div>
                <div className="text-sm"><Prompt text={inst.prompt} /></div>
                {inst.code && <pre className="code-block mt-3 !p-3 !text-[11px]">{inst.code}</pre>}
                {inst.options && <ul className="mt-2 list-disc pl-5 text-xs text-ink/70">{inst.options.map((o: string, j: number) => <li key={j}>{o}</li>)}</ul>}
              </div>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}

export default function VacancyApps() {
  const { id } = useParams<{ id: string }>();
  const { data: v } = useApi<Vacancy>(`/vacancies/${id}`);
  const { data: apps, mutate } = useApi<any[]>(`/employer/vacancies/${id}/applications`);
  const [tab, setTab] = useState<"apps" | "test">("apps");
  if (!v || !apps) return <Loading />;
  async function setStatus(appId: number, status: string) {
    await api(`/employer/applications/${appId}/status`, { body: { status, reason: status === "rejected" ? "other" : undefined } });
    mutate();
  }
  return (
    <>
      <Link href="/employer/vacancies" className="text-sm font-semibold text-ink/50 hover:text-plum">Вакансии</Link>
      <h1 className="mt-1 text-2xl font-extrabold sm:text-[28px]">{v.title}</h1>
      <div className="mb-3 mt-1 text-[15px] text-ink/65">{v.specialization_name}, {v.grade_name}; {rubRange(v.salary_from, v.salary_to)}</div>
      <div className="mb-6"><SkillNames slugs={v.must_skills} /></div>
      <div className="mb-5 max-w-md"><Tabs value={tab} onChange={setTab} items={[{ value: "apps", label: `Отклики (${apps.length})` }, { value: "test", label: "Тест под вакансию" }]} /></div>
      {tab === "test" ? <Blueprint id={id} /> : apps.length === 0 ? <Empty title="Откликов пока нет" text="Кандидаты видят вакансию в общем списке. Пока ждёте — посмотрите подборку по категории." /> : (
        <div className="space-y-3">
          {apps.map((a) => (
            <div key={a.id} className="panel p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <Link href={`/employer/candidates/${a.candidate.id}`} className="text-lg font-bold text-plum hover:underline">{a.candidate.name}</Link>
                  <div className="text-sm text-ink/60">{a.candidate.category.label}; отклик {dateRu(a.created_at)}</div>
                  {a.candidate.contacts && <div className="mt-1 text-sm">Контакты: <b>{[a.candidate.contacts.email, a.candidate.contacts.phone, a.candidate.contacts.telegram].filter(Boolean).join(", ")}</b></div>}
                </div>
                <div className="flex items-center gap-2">
                  {a.match?.score !== undefined && <Chip>совпадение {Math.round(a.match.score)}</Chip>}
                  <StatusChip status={a.status} />
                </div>
              </div>
              {a.match?.explanation && <p className="mt-2 text-sm text-ink/70">{a.match.explanation.summary}</p>}
              {a.cover_letter && <p className="mt-2 rounded-lg bg-mist-50 p-3 text-sm">{a.cover_letter}</p>}
              {(a.status === "sent" || a.status === "viewed") && (
                <div className="mt-3 flex gap-2">
                  <Button size="sm" onClick={() => setStatus(a.id, "accepted")}>Пригласить к общению</Button>
                  <Button size="sm" variant="ghost" onClick={() => setStatus(a.id, "rejected")}>Отказать</Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
