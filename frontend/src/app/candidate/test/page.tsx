"use client";
import clsx from "clsx";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { LevelScale } from "@/components/domain";
import { Button, Chip, ErrorNote, Loading, PageHead, Panel, StatusChip } from "@/components/ui";
import { api, dateRu, useApi } from "@/lib/api";
import { useDict } from "@/lib/session";
import type { Attempt } from "@/lib/types";

function TestHome() {
  const { data: st } = useApi<any>("/candidate/status");
  const { dict, gradeName } = useDict();
  const router = useRouter();
  const pre = useSearchParams().get("grade");
  const [grade, setGrade] = useState<string | null>(pre);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (!st || !dict) return <Loading />;
  if (!st.category.specialization)
    return (
      <>
        <PageHead title="Тестирование" />
        <Panel><p>Сначала пройдите короткий опрос — от него зависит, какой тест вы получите.</p><Button href="/candidate/onboarding" className="mt-4">Пройти опрос</Button></Panel>
      </>
    );
  const av = st.availability || {};
  const chosen = grade || (st.category.grade ? null : st.claimed_grade);

  async function start() {
    setBusy(true);
    setErr(null);
    try {
      const a = await api<Attempt>("/tests/start", { body: { target_grade: chosen } });
      router.push(`/candidate/test/${a.id}`);
    } catch (e) { setErr(e); setBusy(false); }
  }

  return (
    <>
      <PageHead title="Тестирование" sub={`Специализация: ${st.category.specialization_name}. Тест адаптивный: следующий вопрос зависит от ваших ответов.`} />
      {st.active_attempt_id && (
        <Panel className="mb-6 border-signal/40">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="font-semibold">У вас есть незавершённый тест.</p>
            <Button href={`/candidate/test/${st.active_attempt_id}`}>Продолжить</Button>
          </div>
        </Panel>
      )}
      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <Panel title="На какой грейд проверяем?">
          <div className="grid gap-3 sm:grid-cols-3">
            {["junior", "middle", "senior"].map((g) => {
              const a = av[g] || {};
              const isCur = st.category.grade === g;
              return (
                <button key={g} disabled={!a.allowed} onClick={() => setGrade(g)}
                        className={clsx("rounded-xl border-2 p-4 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-55",
                          chosen === g ? "border-plum bg-plum-50" : "border-mist-300 hover:border-plum/40")}>
                  <div className="text-lg font-extrabold text-plum">{gradeName(g)}</div>
                  <div className="mt-1 text-xs text-ink/60">{dict.grades.find((x) => x.slug === g)?.experience}</div>
                  <div className="mt-2">
                    {isCur ? <Chip tone="ok">ваш грейд</Chip> : !a.allowed ? <span className="text-xs text-ink/60">доступно с {dateRu(a.allowed_at)}</span> : null}
                  </div>
                </button>
              );
            })}
          </div>
          {chosen && !av[chosen]?.allowed && av[chosen]?.reason && <p className="mt-3 text-sm text-warn">{av[chosen].reason}</p>}
          <ul className="mt-5 space-y-1.5 text-sm text-ink/70">
            <li>От 8 до 25 заданий: код, SQL, конфигурации, вопросы на понимание. Если результат у самой границы грейда — до 35, чтобы решение было увереннее.</li>
            <li>На каждое задание — ограничение по времени, оно показано над вопросом.</li>
            <li>Задания уникальны: у другого кандидата будут другие числа, код и варианты.</li>
            <li>Закрыть тест и начать заново нельзя: незавершённый тест продолжится с того же места.</li>
          </ul>
          <ErrorNote error={err} />
          <Button className="mt-5" size="lg" onClick={start} loading={busy} disabled={!chosen || !av[chosen]?.allowed}>
            Начать тест{chosen ? ` на ${gradeName(chosen)}` : ""}
          </Button>
        </Panel>
        <Panel title="Ваш уровень сейчас">
          {st.theta !== null ? <LevelScale theta={st.theta} se={st.theta_se} current={st.category.grade} /> : <p className="text-sm text-ink/60">Появится после первого теста.</p>}
          <p className="mt-4 text-sm text-ink/60">Смена грейда — не чаще раза в 90 дней. Повторная попытка на тот же грейд — через 14 дней.</p>
        </Panel>
      </div>
      {st.attempts?.length > 0 && (
        <Panel title="История тестов" className="mt-6">
          <div className="divide-y divide-mist">
            {st.attempts.map((a: Attempt) => (
              <a key={a.id} href={`/candidate/test/${a.id}`} className="flex flex-wrap items-center gap-3 py-3 hover:bg-mist-50">
                <span className="w-48 font-semibold text-plum">{a.kind === "vacancy" ? "Под вакансию" : a.kind === "confirm" ? `Подтверждение ${gradeName(a.target_grade)}` : `Тест на ${gradeName(a.target_grade)}`}</span>
                <StatusChip status={a.status === "in_progress" ? "in_progress" : a.outcome || ""} />
                <span className="text-sm text-ink/55">{dateRu(a.started_at)}, заданий: {a.n_answered}</span>
              </a>
            ))}
          </div>
          {st.grade_history?.length > 0 && (
            <div className="mt-4 text-sm text-ink/65">
              <div className="font-semibold text-plum">Изменения грейда</div>
              {st.grade_history.map((h: any, i: number) => (
                <div key={i}>{dateRu(h.at)}: {h.from ? `${gradeName(h.from)} → ` : ""}{gradeName(h.to)} ({h.reason})</div>
              ))}
            </div>
          )}
        </Panel>
      )}
    </>
  );
}

export default function Page() {
  return <Suspense><TestHome /></Suspense>;
}
