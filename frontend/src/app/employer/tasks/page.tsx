"use client";
import Link from "next/link";
import { useState } from "react";
import { Button, Chip, Empty, ErrorNote, Field, Loading, Modal, MultiPick, PageHead, Panel } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { useDict } from "@/lib/session";

function Answers({ taskId }: { taskId: number }) {
  const { data, mutate } = useApi<any[]>(`/employer/tasks/${taskId}/answers`);
  if (!data) return <Loading />;
  if (!data.length) return <p className="text-sm text-ink/55">Ответов пока нет.</p>;
  return (
    <div className="space-y-3">
      {data.map((a) => (
        <div key={a.id} className="rounded-xl border border-mist-300 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Link href={`/employer/candidates/${a.candidate.id}`} className="font-bold text-plum hover:underline">{a.candidate.name}</Link>
            <span className="text-sm">авто: <b>{a.auto_score}</b>/10{a.auto_feedback?.llm_status === "pending" ? " (уточняется)" : ""}{a.employer_score !== null ? <>; ваша: <b>{a.employer_score}</b>/10</> : null}</span>
          </div>
          <p className="mt-2 whitespace-pre-line text-sm">{a.answer}</p>
          {a.employer_score === null && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {[3, 5, 7, 9, 10].map((s) => (
                <Button key={s} size="sm" variant="secondary" onClick={async () => { await api(`/employer/task-answers/${a.id}/review`, { body: { score: s } }); mutate(); }}>{s}</Button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export default function EmpTasks() {
  const { data, mutate } = useApi<any[]>("/employer/tasks");
  const { dict, skillName } = useDict();
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<number | null>(null);
  const [f, setF] = useState({ title: "", body: "", specialization: "backend", skills: [] as string[], min_grade: "junior", criteria: "" });
  const [err, setErr] = useState<unknown>(null);
  if (!data || !dict) return <Loading />;
  async function create() {
    setErr(null);
    try {
      const rubric = f.criteria.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
        const [criterion, kw] = l.split(":");
        return { criterion: criterion.trim(), keywords: (kw || criterion).split(",").map((x) => x.trim().toLowerCase()).filter(Boolean), weight: 1 };
      });
      await api("/employer/tasks", { body: { ...f, rubric } });
      setOpen(false);
      mutate();
    } catch (e) { setErr(e); }
  }
  const spec = dict.specializations.find((s) => s.slug === f.specialization);
  return (
    <>
      <PageHead title="Короткие задания" sub="Раз в неделю система предлагает кандидатам подходящей категории одно из ваших заданий: решить или предложить подход. Вы получаете свежий сигнал, кандидаты — повод обновить профиль."
                action={<Button onClick={() => setOpen(true)}>Новое задание</Button>} />
      {data.length === 0 ? <Empty title="Заданий пока нет" /> : (
        <div className="space-y-4">
          {data.map((t) => (
            <Panel key={t.id} title={t.title} action={<span className="text-sm text-ink/60">предложено {t.stats.offered}, ответов {t.stats.submitted}</span>}>
              <p className="text-[15px] text-ink/75">{t.body}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">{t.skill_names.map((s: string) => <Chip key={s} tone="mist">{s}</Chip>)}</div>
              <Button size="sm" variant="secondary" className="mt-4" onClick={() => setView(view === t.id ? null : t.id)}>{view === t.id ? "Скрыть ответы" : "Ответы кандидатов"}</Button>
              {view === t.id && <div className="mt-4"><Answers taskId={t.id} /></div>}
            </Panel>
          ))}
        </div>
      )}
      <Modal open={open} onClose={() => setOpen(false)} title="Новое задание" wide>
        <div className="space-y-4">
          <Field label="Название"><input className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          <Field label="Условие"><textarea className="input min-h-28" value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Специализация">
              <select className="input" value={f.specialization} onChange={(e) => setF({ ...f, specialization: e.target.value, skills: [] })}>
                {dict.specializations.map((s) => <option key={s.slug} value={s.slug}>{s.name}</option>)}
              </select>
            </Field>
            <Field label="Минимальный грейд">
              <select className="input" value={f.min_grade} onChange={(e) => setF({ ...f, min_grade: e.target.value })}>
                {dict.grades.map((g) => <option key={g.slug} value={g.slug}>{g.name}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Навыки"><MultiPick options={(spec?.core_skills || []).map((s) => ({ value: s, label: skillName(s) }))} value={f.skills} onChange={(v) => setF({ ...f, skills: v })} /></Field>
          <Field label="Критерии оценки" hint="По одному в строке. После двоеточия — ключевые слова для автооценки без LLM, например: «План запроса: explain, план»">
            <textarea className="input min-h-24" value={f.criteria} onChange={(e) => setF({ ...f, criteria: e.target.value })} />
          </Field>
          <ErrorNote error={err} />
          <div className="flex justify-end gap-3"><Button variant="ghost" onClick={() => setOpen(false)}>Отмена</Button><Button onClick={create}>Создать</Button></div>
        </div>
      </Modal>
    </>
  );
}
