"use client";
import clsx from "clsx";
import { useEffect, useState } from "react";
import { api, dateRu, results } from "@/lib/api";
import { useDict } from "@/lib/session";
import type { Explanation, FspMatch, FspView, SkillView } from "@/lib/types";
import { Chip, Modal, Loading, ErrorNote } from "./ui";

// ---------------------------------------------------------------- шкала уровня
const MIN = -2.6;
const MAX = 2.6;
const pct = (x: number) => `${((Math.min(MAX, Math.max(MIN, x)) - MIN) / (MAX - MIN)) * 100}%`;
const BANDS = [
  { slug: "intern", name: "Стажёр", from: MIN, to: -1, cls: "bg-plum-50" },
  { slug: "junior", name: "Junior", from: -1, to: 0, cls: "bg-plum-100" },
  { slug: "middle", name: "Middle", from: 0, to: 1, cls: "bg-lavender-200" },
  { slug: "senior", name: "Senior", from: 1, to: MAX, cls: "bg-lavender" },
];

/** Положение кандидата на шкале способности с интервалом неопределённости и порогами грейдов. */
export function LevelScale({ theta, se, current, target, z = 1.645, compact, label = "Ваш результат" }: {
  theta?: number | null; se?: number | null; current?: string | null; target?: string | null; z?: number; compact?: boolean; label?: string;
}) {
  const has = theta !== null && theta !== undefined;
  const lo = has && se ? theta - z * se : null;
  const hi = has && se ? theta + z * se : null;
  return (
    <div className={clsx("select-none", compact ? "pt-5" : "pt-8")}>
      <div className={clsx("relative rounded-lg", compact ? "h-7" : "h-10")}>
        {BANDS.map((b) => (
          <div
            key={b.slug}
            className={clsx("absolute inset-y-0 border-r border-white", b.cls, b.slug === "intern" && "rounded-l-lg", b.slug === "senior" && "rounded-r-lg",
              current === b.slug && "ring-2 ring-inset ring-plum")}
            style={{ left: pct(b.from), width: `calc(${pct(b.to)} - ${pct(b.from)})` }}
          />
        ))}
        {target && target !== "intern" && (
          <div className="absolute -inset-y-1.5 w-0 border-l-2 border-dashed border-plum" style={{ left: pct(BANDS.find((b) => b.slug === target)!.from) }}
               title={`Порог ${target}`} />
        )}
        {lo !== null && hi !== null && (
          <div className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-signal/35" style={{ left: pct(lo), width: `calc(${pct(hi)} - ${pct(lo)})` }} />
        )}
        {has && (
          <div className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2" style={{ left: pct(theta!) }}>
            <div className={clsx("rounded-full border-[3px] border-white bg-signal shadow-md", compact ? "h-4 w-4" : "h-5 w-5")} />
            <div className={clsx("absolute left-1/2 -translate-x-1/2 whitespace-nowrap font-bold text-signal", compact ? "-top-6 text-2xs" : "-top-8 text-xs")}>
              {label}
            </div>
          </div>
        )}
      </div>
      <div className="relative mt-1.5 h-5 text-2xs font-semibold text-plum/70">
        {BANDS.map((b) => (
          <span key={b.slug} className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: `calc((${pct(b.from)} + ${pct(b.to)}) / 2)` }}>
            {b.name}
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- оценка
export function ScoreBar({ value, max = 100, tone = "plum" }: { value: number; max?: number; tone?: "plum" | "signal" }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-mist">
      <div className={clsx("h-full rounded-full", tone === "signal" ? "bg-signal" : "bg-plum")} style={{ width: `${Math.max(2, (value / max) * 100)}%` }} />
    </div>
  );
}

export function MatchScore({ score }: { score: number }) {
  return (
    <div className="flex h-16 w-16 shrink-0 flex-col items-center justify-center self-start rounded-xl bg-plum text-white" title="Соответствие потребности, из 100">
      <span className="text-2xl font-extrabold tabular-nums leading-none">{Math.round(score)}</span>
      <span className="mt-0.5 text-[10px] font-semibold text-white/70">из 100</span>
    </div>
  );
}

// ---------------------------------------------------------------- навыки с доказательствами
export function SkillList({ skills, candidateId, showEvidence = true, limit }: { skills: SkillView[]; candidateId?: number; showEvidence?: boolean; limit?: number }) {
  const [open, setOpen] = useState<string | null>(null);
  const [ev, setEv] = useState<number | null>(null);
  const tested = skills.filter((s) => s.score !== null);
  const fspOnly = skills.filter((s) => s.score === null && (s.fsp_level ?? 0) >= 0.25);
  const list = limit ? tested.slice(0, limit) : tested;
  if (!tested.length && !fspOnly.length) return <p className="text-sm text-ink/55">Подтверждённых навыков пока нет — они появятся после теста.</p>;
  return (
    <div className="divide-y divide-mist">
      {list.map((s) => (
        <div key={s.slug} className="py-2.5">
          <div className="flex items-center gap-3">
            <div className="w-40 shrink-0 text-sm font-semibold sm:w-48">{s.name}</div>
            <div className="flex-1">{s.score !== null ? <ScoreBar value={s.score} /> : <div className="text-xs text-ink/50">только по данным ФСП</div>}</div>
            <div className={clsx("w-14 text-right text-sm font-bold tabular-nums", s.n <= 2 ? "text-plum/45" : "text-plum")}
                 title={s.n <= 2 ? "Предварительная оценка: мало заданий по навыку" : undefined}>{s.score ?? "—"}</div>
            {showEvidence && (s.evidence?.length || s.fsp_evidence?.length) ? (
              <button className="text-xs font-semibold text-plum underline decoration-signal/40 underline-offset-2" onClick={() => setOpen(open === s.slug ? null : s.slug)}>
                {open === s.slug ? "Скрыть" : "Доказательства"}
              </button>
            ) : null}
          </div>
          <div className="mt-1 flex flex-wrap gap-1.5 pl-0 sm:pl-[12.75rem]">
            {s.n > 0 && <span className="text-2xs text-ink/55">верно {s.n_correct} из {s.n} {s.n === 1 ? "задания" : "заданий"}{s.n <= 2 ? ", оценка предварительная" : `, уверенность ${s.confidence}`}</span>}
            {s.fsp_confirmed && <Chip tone="signal" className="!text-[11px]">подтверждено ФСП</Chip>}
          </div>
          {open === s.slug && (
            <div className="mt-2 rounded-xl bg-mist-50 p-3 text-sm">
              {s.evidence?.map((e) => (
                <div key={e.response_id} className="flex flex-wrap items-center gap-2 py-1">
                  <span className={clsx("h-2 w-2 rounded-full", e.correct ? "bg-ok" : "bg-signal")} aria-hidden />
                  <span className="font-medium">{e.title}</span>
                  <span className="text-ink/50">уровень {e.level}, {e.correct ? "верно" : "неверно"}, {dateRu(e.date)}</span>
                  {candidateId && (
                    <button className="text-xs font-semibold text-plum underline" onClick={() => setEv(e.response_id)}>открыть задание</button>
                  )}
                </div>
              ))}
              {s.fsp_evidence?.map((e, i) => (
                <div key={i} className="py-1 text-ink/75">
                  ФСП: {e.event}, место {e.place} из {e.participants_total} ({dateRu(e.date)}){e.role ? `, роль: ${e.role}` : ""}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
      {fspOnly.length > 0 && !limit && (
        <div className="py-3 text-sm">
          <span className="text-ink/55">Встречается в результатах ФСП, тестом не проверялось: </span>
          {fspOnly.map((s) => s.name).join(", ")}
        </div>
      )}
      {candidateId && <EvidenceModal candidateId={candidateId} responseId={ev} onClose={() => setEv(null)} />}
    </div>
  );
}

function EvidenceModal({ candidateId, responseId, onClose }: { candidateId: number; responseId: number | null; onClose: () => void }) {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => {
    if (!responseId) return;
    setData(null);
    setErr(null);
    api(`/employer/candidates/${candidateId}/evidence/${responseId}`).then(setData).catch(setErr);
  }, [candidateId, responseId]);
  const optText = (i: number) => data?.options?.[i];
  const fmtAns = (v: any) =>
    data?.fmt === "single" ? optText(Number(v)) : data?.fmt === "multi" ? (v || []).map((i: number) => optText(i)).join("; ") : Array.isArray(v) ? v[0] : String(v ?? "—");
  return (
    <Modal open={!!responseId} onClose={onClose} title="Задание, которое решал кандидат" wide>
      <ErrorNote error={err} />
      {!data ? <Loading /> : (
        <div className="space-y-4">
          <p className="text-sm text-ink/60">
            Экземпляр шаблона «{data.title}» уникален для этого кандидата — по нему нельзя восстановить задания других людей.
            Трудность b = {data.difficulty_b.toFixed(2)}, дискриминативность a = {data.discrimination_a.toFixed(2)}.
          </p>
          <Prompt text={data.prompt} />
          {data.code && <pre className="code-block">{data.code}</pre>}
          {data.options && (
            <ul className="space-y-1.5 text-sm">
              {data.options.map((o: string, i: number) => (
                <li key={i} className="rounded-lg border border-mist-300 px-3 py-2">{o}</li>
              ))}
            </ul>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl bg-mist-50 p-3">
              <div className="text-xs text-ink/55">Ответ кандидата</div>
              <div className="font-semibold">{fmtAns(data.candidate_answer)}</div>
            </div>
            <div className="rounded-xl bg-mist-50 p-3">
              <div className="text-xs text-ink/55">Правильный ответ</div>
              <div className="font-semibold">{fmtAns(data.correct_answer)}</div>
            </div>
          </div>
          <Chip tone={data.is_correct ? "ok" : "signal"}>{data.is_correct ? "Решено верно" : "Ошибка"}</Chip>
        </div>
      )}
    </Modal>
  );
}

/** Текст задания: поддержка **жирного** и переносов строк без HTML-инъекций. */
export function Prompt({ text }: { text: string }) {
  return (
    <div className="space-y-2 text-[15px] leading-relaxed">
      {text.split("\n").map((line, i) => (
        <p key={i}>
          {line.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, j) =>
            part.startsWith("**") ? <strong key={j}>{part.slice(2, -2)}</strong> : part.startsWith("`") ? <code key={j} className="rounded bg-mist px-1 font-mono text-[13px]">{part.slice(1, -1)}</code> : part,
          )}
        </p>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- ФСП
const yearOf = (d?: string) => (d ? d.slice(0, 4) : "");

/** Строка лучшего результата для карточки в выдаче: «Призёр, 2 место из 120 · Всероссийские · 2025». */
export function FspBadge({ fsp }: { fsp?: FspView }) {
  if (!fsp || fsp.hidden || !fsp.has_history || !fsp.best) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5 text-xs">
      <Chip tone="signal">ФСП</Chip>
      <span className="font-semibold text-plum">{fsp.best.result}</span>
      <span className="text-ink/55">· {fsp.best.level_name} · {yearOf(fsp.best.date)}</span>
      {fsp.prizes > 1 && <span className="text-ink/55">· призовых мест: {fsp.prizes}</span>}
    </span>
  );
}

export function FspBlock({ fsp, compact, own }: { fsp: FspView; compact?: boolean; own?: boolean }) {
  const { skillName } = useDict();
  if (fsp.hidden) return <p className="text-sm text-ink/55">Кандидат скрыл достижения ФСП.</p>;
  if (!fsp.linked)
    return (
      <div className="text-sm text-ink/60">
        <p>ФСП ID не привязан. Это не влияет на категорию: она определяется тестом.</p>
        {own && <p className="mt-2">Привяжите ФСП ID в <a href="/candidate/settings" className="font-semibold text-plum underline">настройках</a> — подтверждённые результаты соревнований поднимут вас в выдаче под запросы, где они подтверждают нужные навыки.</p>}
      </div>
    );
  if (!fsp.has_history)
    return <p className="text-sm text-ink/55">ФСП ID привязан, результатов соревнований пока нет. Это не минус: позиция в выдаче определяется тестом, а результаты появятся здесь после первых стартов.</p>;
  const maxS = fsp.max_strength || Math.max(...(fsp.items || []).map((i) => i.strength || 0), 0.0001);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <Chip tone="signal">{results(fsp.total)}</Chip>
        {fsp.prizes > 0 && <Chip tone="signal">призовых мест: {fsp.prizes}</Chip>}
        {fsp.sport_rank && <Chip tone="plum">{fsp.sport_rank}</Chip>}
      </div>
      {fsp.best && (
        <div className="rounded-xl bg-signal-50 px-4 py-3">
          <div className="text-xs text-ink/55">Сильнейший результат</div>
          <div className="font-bold text-plum">{fsp.best.result}</div>
          <div className="text-sm text-ink/70">{fsp.best.event} · {fsp.best.level_name} · {yearOf(fsp.best.date)}</div>
        </div>
      )}
      {compact && !fsp.items && Object.values(fsp.by_discipline || {}).length > 0 && (
        <ul className="space-y-1 text-sm">
          {Object.values(fsp.by_discipline).map((d) => (
            <li key={d.name}><span className="font-semibold">{d.name}</span>: {d.count} старт., лучшее место {d.best_place}</li>
          ))}
        </ul>
      )}
      {fsp.items && (
        <div className="divide-y divide-mist rounded-xl border border-mist-300/70">
          {(compact ? fsp.items.slice(0, 3) : fsp.items).map((it) => (
            <div key={it.id} className="space-y-1.5 px-4 py-3 text-sm">
              <div className="flex flex-wrap items-start gap-x-4 gap-y-1">
                <div className="min-w-0 flex-1">
                  <div className="font-semibold">{it.event_name}</div>
                  <div className="text-ink/55">
                    {dateRu(it.date)}, {it.level_name.toLowerCase()}
                    {it.team_name ? `, команда «${it.team_name}»` : ""}{it.role ? `, ${it.role}` : ""}
                    {it.tasks_total ? `, решено ${it.tasks_solved} из ${it.tasks_total}` : ""}
                  </div>
                </div>
                <div className="text-right">
                  <div className={clsx("font-bold tabular-nums", it.is_prize ? "text-signal" : "text-plum")}>{it.place} место</div>
                  <div className="text-xs text-ink/50">из {it.participants_total}</div>
                </div>
              </div>
              {it.strength != null && (
                <div className="flex items-center gap-3">
                  <span className="w-28 shrink-0 text-xs text-ink/55">Сила результата</span>
                  <div className="flex-1"><ScoreBar value={it.strength} max={maxS} tone="signal" /></div>
                  <span className="w-24 shrink-0 text-right text-xs text-ink/60">{it.result?.split(",")[0]}</span>
                </div>
              )}
              {it.skills && it.skills.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 text-xs">
                  <span className="text-ink/55">подтверждает:</span>
                  {it.skills.slice(0, 6).map((s) => <Chip key={s} tone="lavender" className="!text-[11px]">{skillName(s)}</Chip>)}
                </div>
              )}
              <div>
                {it.verified ? <Chip tone="ok">подпись ФСП проверена</Chip> : <Chip tone="warn">подпись не проверена</Chip>}{" "}
                <a href={it.protocol_url} target="_blank" rel="noreferrer" className="text-xs font-semibold text-plum underline">протокол</a>
              </div>
            </div>
          ))}
        </div>
      )}
      {!compact && <p className="text-xs text-ink/50">Сила результата — уровень соревнования × место с упором на призовые × размер поля × давность. Под конкретный запрос она умножается на то, насколько результат подтверждает нужные навыки.</p>}
    </div>
  );
}

/** Вклад ФСП под конкретный запрос работодателя. */
export function FspMatchView({ m }: { m: FspMatch }) {
  const { skillName } = useDict();
  if (!m.has_history) return <p className="text-sm text-ink/55">Истории ФСП нет — это не штраф: место в выдаче определяют тест и условия.</p>;
  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-3">
        <span className="w-44 shrink-0 text-ink/75">ФСП под этот запрос</span>
        <div className="flex-1"><ScoreBar value={m.value} max={1} tone="signal" /></div>
        <span className="w-24 text-right text-xs tabular-nums text-ink/60">+{m.points.toFixed(1)} балла</span>
      </div>
      {m.items.length === 0 ? <p className="text-ink/55">Результаты есть, но слабо связаны с требованиями запроса.</p> : (
        <ul className="space-y-1.5">
          {m.items.map((it, i) => (
            <li key={i} className="rounded-lg bg-mist-50 px-3 py-2">
              <div><b>{it.result}</b> — {it.event} ({yearOf(it.date)}{it.level ? `, ${it.level.toLowerCase()}` : ""})</div>
              <div className="text-xs text-ink/60">
                связь с запросом {Math.round(it.relevance * 100)}%
                {it.matched_skills.length > 0 && <> · подтверждает: {it.matched_skills.map(skillName).join(", ")}</>}
                {it.role ? ` · роль: ${it.role}` : ""}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- объяснение выдачи
export function ExplanationView({ e, compact }: { e: Explanation; compact?: boolean }) {
  const { gradeName } = useDict();
  return (
    <div className="space-y-3 text-sm">
      {e.borderline && (
        <div className="rounded-lg bg-amber-50 px-3 py-2 text-warn">
          {e.borderline.p >= 0.7 ? `Уровень ${gradeName(e.borderline.to)} вероятен` : `На границе с грейдом ${gradeName(e.borderline.to)}`}: вероятность {Math.round(e.borderline.p * 100)}% по оценке теста и её погрешности. Категория по тесту не меняется (тест на {gradeName(e.borderline.to)} кандидат не сдавал), в выдаче он идёт с этой вероятностью вместо полного совпадения грейда.
        </div>
      )}
      <div className={clsx("grid gap-3", e.cons.length > 0 && "sm:grid-cols-2")}>
        <div>
          <div className="mb-1 font-semibold text-ok">Почему в подборке</div>
          <ul className="space-y-1">{e.pros.map((p, i) => <li key={i} className="flex gap-2"><span className="text-ok">+</span>{p}</li>)}</ul>
        </div>
        {e.cons.length > 0 && (
          <div>
            <div className="mb-1 font-semibold text-warn">На что обратить внимание</div>
            <ul className="space-y-1">{e.cons.map((p, i) => <li key={i} className="flex gap-2"><span className="text-warn">−</span>{p}</li>)}</ul>
          </div>
        )}
      </div>
      {!compact && e.fsp && (
        <div>
          <div className="mb-2 font-semibold text-plum">Достижения ФСП под запрос</div>
          <FspMatchView m={e.fsp} />
        </div>
      )}
      {!compact && (
        <div>
          <div className="mb-2 font-semibold text-plum">Из чего сложилась оценка</div>
          <div className="space-y-1.5">
            {e.factors.map((f) => (
              <div key={f.key} className="flex items-center gap-3">
                <div className="w-44 shrink-0 text-ink/75">{f.name}</div>
                <div className="flex-1"><ScoreBar value={f.value} max={1} tone="signal" /></div>
                <div className="w-24 text-right text-xs tabular-nums text-ink/60">{f.points.toFixed(1)} из {Math.round(f.weight * 100)}</div>
              </div>
            ))}
          </div>
          {e.salary_multiplier != null && e.salary_multiplier < 0.99 && (
            <p className="mt-2 text-xs text-warn">Ожидания кандидата выше максимума вилки: итог умножен на {e.salary_multiplier.toFixed(2).replace(".", ",")}.</p>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- динамика оценки во время теста
export function TraceChart({ trace, cut }: { trace: { n: number; theta: number; se: number }[]; cut?: number }) {
  if (trace.length < 2) return null;
  const W = 560, H = 180, P = 28;
  const x = (n: number) => P + ((n - 1) / Math.max(1, trace.length - 1)) * (W - 2 * P);
  const y = (t: number) => H - P - ((Math.max(-3, Math.min(3, t)) + 3) / 6) * (H - 2 * P);
  const band = trace.map((p) => `${x(p.n)},${y(p.theta + 1.645 * p.se)}`).join(" ") + " " +
    [...trace].reverse().map((p) => `${x(p.n)},${y(p.theta - 1.645 * p.se)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Как уточнялась оценка уровня по мере ответов">
      <polygon points={band} fill="#FF0053" opacity="0.12" />
      {cut !== undefined && (
        <>
          <line x1={P} x2={W - P} y1={y(cut)} y2={y(cut)} stroke="#2D1451" strokeDasharray="5 4" />
          <text x={W - P} y={y(cut) - 6} textAnchor="end" fontSize="11" fill="#2D1451" fontWeight="600">порог грейда</text>
        </>
      )}
      <polyline points={trace.map((p) => `${x(p.n)},${y(p.theta)}`).join(" ")} fill="none" stroke="#FF0053" strokeWidth="2.5" />
      {trace.map((p) => <circle key={p.n} cx={x(p.n)} cy={y(p.theta)} r="3" fill="#FF0053" />)}
      <text x={P} y={H - 6} fontSize="11" fill="#1C1D22" opacity="0.5">задание 1</text>
      <text x={W - P} y={H - 6} fontSize="11" fill="#1C1D22" opacity="0.5" textAnchor="end">задание {trace.length}</text>
    </svg>
  );
}

export function SkillNames({ slugs, tone = "plum" }: { slugs: string[]; tone?: "plum" | "mist" }) {
  const { skillName } = useDict();
  return (
    <div className="flex flex-wrap gap-1.5">
      {slugs.map((s) => <Chip key={s} tone={tone}>{skillName(s)}</Chip>)}
    </div>
  );
}
