"use client";
import Link from "next/link";
import { useState } from "react";
import { NeedDraft, NeedForm, NeedParser } from "@/components/employer";
import { Button, Chip, Empty, ErrorNote, Field, Loading, Modal, PageHead, StatusChip } from "@/components/ui";
import { api, rubRange, useApi } from "@/lib/api";
import type { Vacancy } from "@/lib/types";

export default function EmpVacancies() {
  const { data, mutate } = useApi<Vacancy[]>("/employer/vacancies");
  const [draft, setDraft] = useState<NeedDraft | null>(null);
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (!data) return <Loading />;

  async function publish() {
    if (!draft) return;
    setBusy(true);
    setErr(null);
    try {
      await api("/employer/vacancies", { body: {
        title: draft.title, description: draft.description || draft.title, specialization: draft.specialization, grade: draft.grades[0] || "middle",
        must_skills: draft.must_skills, nice_skills: draft.nice_skills, work_format: draft.work_formats[0] || "hybrid", city: draft.city || null,
        salary_from: draft.salary_from, salary_to: draft.salary_to } });
      setCreating(false);
      setDraft(null);
      mutate();
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }

  return (
    <>
      <PageHead title="Вакансии и отклики" sub="Дополнительный канал: кандидаты, которым вы ещё не написали, могут откликнуться сами. Вилка в вакансии обязательна."
                action={<Button onClick={() => setCreating(true)}>Опубликовать вакансию</Button>} />
      {data.length === 0 ? <Empty title="Вакансий пока нет" /> : (
        <div className="space-y-3">
          {data.map((v) => (
            <Link key={v.id} href={`/employer/vacancies/${v.id}`} className="panel block p-5 hover:border-plum/40">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-lg font-bold text-plum">{v.title}</div>
                  <div className="text-sm text-ink/60">{v.specialization_name}, {v.grade_name}; {rubRange(v.salary_from, v.salary_to)}</div>
                </div>
                <div className="flex items-center gap-2">
                  {v.applications && v.applications.new > 0 && <Chip tone="signal">новых откликов: {v.applications.new}</Chip>}
                  <Chip tone="mist">откликов: {v.applications?.total || 0}</Chip>
                  <StatusChip status={v.status} />
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
      <Modal open={creating} onClose={() => { setCreating(false); setDraft(null); }} title="Новая вакансия" wide>
        {!draft ? <NeedParser onParsed={setDraft} /> : (
          <>
            <NeedForm value={draft} onChange={setDraft} />
            <Field label="Текст вакансии" className="mt-5"><textarea className="input min-h-32" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></Field>
            <p className="mt-2 text-xs text-ink/55">Для вакансии берётся первый выбранный грейд и формат.</p>
            <ErrorNote error={err} />
            <div className="mt-5 flex justify-end gap-3">
              <Button variant="ghost" onClick={() => setDraft(null)}>Назад к тексту</Button>
              <Button onClick={publish} loading={busy} disabled={!draft.salary_from || !draft.salary_to}>Опубликовать</Button>
            </div>
          </>
        )}
      </Modal>
    </>
  );
}
