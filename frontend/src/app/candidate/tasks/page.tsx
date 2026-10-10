"use client";
import { useState } from "react";
import { Button, Chip, Empty, ErrorNote, Loading, PageHead, Panel, StatusChip } from "@/components/ui";
import { api, dateRu, useApi } from "@/lib/api";

function TaskCard({ a, onDone }: { a: any; onDone: () => void }) {
  const [text, setText] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function submit() {
    setBusy(true);
    setErr(null);
    try { await api(`/tasks/${a.id}/submit`, { body: { answer: text } }); onDone(); } catch (e) { setErr(e); } finally { setBusy(false); }
  }
  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-lg font-bold text-plum">{a.task.title}</div>
          <div className="text-sm text-ink/60">от компании {a.task.company}, {dateRu(a.created_at)}</div>
        </div>
        <StatusChip status={a.status} />
      </div>
      <p className="mt-4 whitespace-pre-line text-[15px] leading-relaxed">{a.task.body}</p>
      <div className="mt-3 flex flex-wrap gap-1.5">{a.task.skill_names.map((s: string) => <Chip key={s} tone="mist">{s}</Chip>)}</div>
      {a.status === "offered" ? (
        <div className="mt-5">
          <textarea className="input min-h-36" value={text} onChange={(e) => setText(e.target.value)}
                    placeholder="Решение или подход: что сделаете, в каком порядке и почему" aria-label="Ваш ответ" />
          <ErrorNote error={err} />
          <div className="mt-3 flex flex-wrap gap-3">
            <Button onClick={submit} loading={busy} disabled={text.trim().length < 20}>Отправить ответ</Button>
            <Button variant="ghost" onClick={async () => { await api(`/tasks/${a.id}/skip`, { method: "POST" }); onDone(); }}>Пропустить</Button>
          </div>
        </div>
      ) : a.answer ? (
        <div className="mt-5 space-y-3">
          <div className="rounded-xl bg-mist-50 p-4 text-sm"><div className="mb-1 font-semibold">Ваш ответ</div><p className="whitespace-pre-line">{a.answer}</p></div>
          {a.auto_score !== null && (
            <div className="text-sm">
              <span className="font-semibold">Автоматическая оценка: {a.auto_score} из 10.</span>{" "}
              {a.auto_feedback?.llm_status === "pending" && <span className="text-plum">Предварительная, по ключевым словам: модель уточняет оценку по рубрике… </span>}
              {a.auto_feedback?.criteria && <span className="text-ink/65">Учтено: {a.auto_feedback.criteria.filter((c: any) => c.met).map((c: any) => c.criterion).join("; ") || "—"}</span>}
            </div>
          )}
          {a.employer_score !== null && <div className="text-sm"><b>Оценка компании: {a.employer_score} из 10.</b> {a.employer_comment}</div>}
        </div>
      ) : null}
    </Panel>
  );
}

export default function Tasks() {
  // пока модель уточняет оценку ответа (фоном, до полуминуты), список перечитывается каждые 5 с
  const { data, mutate } = useApi<any[]>("/tasks", {
    refreshInterval: (d) => (d?.some((a: any) => a.auto_feedback?.llm_status === "pending") ? 5000 : 0),
  });
  if (!data) return <Loading />;
  return (
    <>
      <PageHead title="Задания от компаний" sub="Раз в неделю система предлагает короткую задачу от работодателей вашей категории: решить её или описать подход. Ответ освежает профиль и поднимает вас в выдаче." />
      {data.length === 0 ? <Empty title="Новых заданий пока нет" text="Задания появляются после присвоения категории. Загляните через несколько дней." /> : (
        <div className="space-y-5">{data.map((a) => <TaskCard key={a.id} a={a} onDone={() => mutate()} />)}</div>
      )}
    </>
  );
}
