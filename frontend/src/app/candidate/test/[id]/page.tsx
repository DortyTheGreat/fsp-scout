"use client";
import clsx from "clsx";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { LevelScale, Prompt, TraceChart } from "@/components/domain";
import { Button, Chip, ErrorNote, Loading, Modal, Panel } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { useDict } from "@/lib/session";
import type { Attempt } from "@/lib/types";

function Timer({ presentedAt, limit }: { presentedAt: string; limit: number }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const left = Math.max(0, Math.round(limit - (now - new Date(presentedAt).getTime()) / 1000));
  const m = Math.floor(left / 60), s = left % 60;
  return (
    <span className={clsx("rounded-lg px-2.5 py-1 font-mono text-sm font-semibold tabular-nums", left < 20 ? "bg-signal text-white" : "bg-mist text-plum")}
          aria-label={`Осталось ${m} мин ${s} сек`}>
      {m}:{String(s).padStart(2, "0")}
    </span>
  );
}

function Runner({ a, onUpdate }: { a: Attempt; onUpdate: (a: Attempt) => void }) {
  const cur = a.current!;
  const [single, setSingle] = useState<number | null>(null);
  const [multi, setMulti] = useState<number[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [quit, setQuit] = useState(false);
  useEffect(() => { setSingle(null); setMulti([]); setText(""); setErr(null); }, [cur.id]);

  const value = cur.fmt === "single" ? single : cur.fmt === "multi" ? multi : text;
  const ready = cur.fmt === "single" ? single !== null : cur.fmt === "multi" ? multi.length > 0 : text.trim().length > 0;

  async function submit(e?: React.FormEvent) {
    e?.preventDefault();
    setBusy(true);
    try {
      onUpdate(await api<Attempt>(`/tests/${a.id}/answer`, { body: { item_id: cur.id, value } }));
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-3xl">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-ink/60">
          Задание <b className="text-plum">{cur.order}</b> <span className="text-ink/45">— обычно всего {a.min_items}–{a.max_items}</span>
        </div>
        <Timer presentedAt={cur.presented_at} limit={cur.time_limit_s} />
      </div>
      <div className="mb-5 h-1.5 overflow-hidden rounded-full bg-mist">
        <div className="h-full bg-signal transition-all" style={{ width: `${Math.min(100, ((cur.order - 1) / a.max_items) * 100)}%` }} />
      </div>
      <Panel>
        <div className="mb-3 text-xs font-semibold text-lavender">{cur.title}</div>
        <Prompt text={cur.prompt} />
        {cur.code && <pre className="code-block mt-4" aria-label="Код к заданию">{cur.code}</pre>}
        <div className="mt-5 space-y-2">
          {cur.fmt === "input" && (
            <input className="input font-mono" autoFocus value={text} onChange={(e) => setText(e.target.value)} placeholder={cur.placeholder || "Ваш ответ"} aria-label="Ответ" />
          )}
          {cur.fmt !== "input" && cur.options?.map((o, i) => {
            const on = cur.fmt === "single" ? single === i : multi.includes(i);
            return (
              <label key={i} className={clsx("flex cursor-pointer items-start gap-3 rounded-xl border-2 px-4 py-3 transition-colors",
                on ? "border-plum bg-plum-50" : "border-mist-300 hover:border-plum/40")}>
                <input type={cur.fmt === "single" ? "radio" : "checkbox"} name="opt" className="mt-1 h-4 w-4 accent-plum" checked={on}
                       onChange={() => cur.fmt === "single" ? setSingle(i) : setMulti(on ? multi.filter((x) => x !== i) : [...multi, i])} />
                <span className={clsx("text-[15px]", /[=<>{}[\]]|^\(|^\w+\(/.test(o) && "font-mono text-sm")}>{o}</span>
              </label>
            );
          })}
          {cur.fmt === "multi" && <p className="text-xs text-ink/55">Можно выбрать несколько вариантов.</p>}
        </div>
        <ErrorNote error={err} />
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
          <button type="button" onClick={() => setQuit(true)} className="text-sm font-semibold text-ink/50 underline underline-offset-4 hover:text-signal">
            Завершить досрочно
          </button>
          <Button type="submit" size="lg" loading={busy} disabled={!ready}>Ответить</Button>
        </div>
      </Panel>
      <Modal open={quit} onClose={() => setQuit(false)} title="Завершить тест досрочно?">
        <p className="text-[15px] text-ink/70">Оставшиеся задания будут засчитаны как неверные, результат сохранится. Повторить тест на этот грейд можно будет через 14 дней.</p>
        <div className="mt-5 flex justify-end gap-3">
          <Button variant="ghost" onClick={() => setQuit(false)}>Продолжить тест</Button>
          <Button variant="danger" onClick={async () => { onUpdate(await api(`/tests/${a.id}/abandon`, { method: "POST" })); setQuit(false); }}>Завершить</Button>
        </div>
      </Modal>
    </form>
  );
}

function Result({ a, reload }: { a: Attempt; reload: () => void }) {
  const d = a.decision;
  const { gradeName } = useDict();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const assigned = d.grade_assigned || d.grade_confirmed;

  async function acceptLower() {
    setBusy(true);
    try { await api(`/tests/${a.id}/accept-lower`, { method: "POST" }); reload(); } catch (e) { setErr(e); } finally { setBusy(false); }
  }
  async function startGrade(g: string) {
    setBusy(true);
    try { const n = await api<Attempt>("/tests/start", { body: { target_grade: g } }); router.push(`/candidate/test/${n.id}`); }
    catch (e) { setErr(e); setBusy(false); }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Panel>
        <div className="text-sm text-ink/55">{a.kind === "vacancy" ? "Тест под вакансию" : a.kind === "confirm" ? `Подтверждающий тест на ${gradeName(a.target_grade)}` : `Тест на ${gradeName(a.target_grade)}`}</div>
        <h1 className="mt-1 text-[28px] font-extrabold">
          {a.outcome === "needs_confirmation" ? "Нужен короткий подтверждающий тест"
            : d.abandoned ? "Тест завершён досрочно" : d.passed ? (assigned ? `Категория подтверждена: ${gradeName(assigned)}` : "Тест пройден") : `Уровень ${gradeName(a.target_grade)} пока не подтверждён`}
        </h1>
        <p className="mt-2 text-[15px] text-ink/70">
          {a.outcome === "needs_confirmation"
            ? "Результат высокий, но ответы плохо согласуются между собой: часть трудных заданий решена, а более простые — нет. Так бывает при случайных ошибках, но так же выглядит и шпаргалка. Пройдите 6–15 заданий из шаблонов, где у каждого кандидата уникальный вариант, — после этого грейд будет присвоен."
            : d.passed
            ? "Работодатели видят вашу категорию, оценки навыков и задания, на которых они основаны."
            : "Грейд не понижается автоматически. Можно принять уровень ниже по этому же результату или пройти отдельный тест."}
        </p>
        <LevelScale theta={d.theta} se={d.se} target={a.target_grade} current={assigned || undefined} />
        <p className="mt-3 text-sm text-ink/60">
          Заданий: {d.n_items}. {d.confident ? "Результат статистически уверенный." : "Результат близок к порогу — решение принято по максимуму заданий."}
          {" "}Вероятность, что ваш уровень выше порога, — {Math.round(d.p_pass * 100)}%.
        </p>
        <ErrorNote error={err} />
        {(d.n_prior_items ?? 0) > 0 && <p className="mt-1 text-sm text-ink/60">Учтены и {d.n_prior_items} ответов предыдущей попытки.</p>}
        <div className="mt-6 flex flex-wrap gap-3">
          {a.outcome === "needs_confirmation" && <Button onClick={() => startGrade(a.target_grade)} loading={busy}>Пройти подтверждающий тест</Button>}
          {a.outcome !== "needs_confirmation" && d.passed && d.upgrade_suggested && a.kind === "grade" && (
            <Button onClick={() => startGrade(d.upgrade_suggested!)} loading={busy}>Попробовать {gradeName(d.upgrade_suggested)}</Button>
          )}
          {!d.passed && d.can_accept_lower && d.lower_grade && d.lower_grade !== "intern" && !d.grade_assigned && (
            <Button onClick={acceptLower} loading={busy}>Принять грейд {gradeName(d.lower_grade)}</Button>
          )}
          {!d.passed && d.lower_grade && d.lower_grade !== "intern" && (
            <Button variant="secondary" onClick={() => startGrade(d.lower_grade!)} loading={busy}>Пройти тест на {gradeName(d.lower_grade)}</Button>
          )}
          <Button variant="ghost" href="/candidate">В личный кабинет</Button>
        </div>
      </Panel>
      <Panel title="Как уточнялась оценка">
        <TraceChart trace={a.trace} cut={d.cut} />
        <p className="mt-2 text-sm text-ink/60">Линия — оценка уровня после каждого ответа, полоса — её неопределённость. Тест останавливается, когда полоса целиком выше или ниже порога.</p>
      </Panel>
      {a.items && (
        <Panel title="Ваши ответы">
          <div className="flex flex-wrap gap-2">
            {a.items.map((it) => (
              <span key={it.order} title={it.title} className={clsx("rounded-lg px-2.5 py-1 text-xs font-semibold", it.correct ? "bg-emerald-50 text-ok" : "bg-signal-50 text-signal-600")}>
                {it.order}. {it.title}
              </span>
            ))}
          </div>
          <p className="mt-3 text-sm text-ink/55">Правильные ответы не показываются, чтобы задания нельзя было собрать в шпаргалку, — хотя у других кандидатов они всё равно будут другими.</p>
        </Panel>
      )}
      {a.kind === "grade" && <Chip tone="mist">Оценки по навыкам обновлены в профиле</Chip>}
    </div>
  );
}

export default function AttemptPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error, mutate } = useApi<Attempt>(`/tests/${id}`);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  if (data.status === "in_progress" && data.current) return <Runner a={data} onUpdate={(a) => mutate(a, { revalidate: false })} />;
  return <Result a={data} reload={() => mutate()} />;
}
