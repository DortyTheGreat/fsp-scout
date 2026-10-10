"use client";
import clsx from "clsx";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Button, ErrorNote, Field, Loading, MultiPick, PageHead, Panel } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { useDict } from "@/lib/session";

const STEPS = ["Направление", "Специализация и стек", "Отрасли", "Уровень", "Условия"];

export default function Onboarding() {
  const { dict } = useDict();
  const router = useRouter();
  const { data: prof } = useApi<any>("/candidate/profile");
  const [step, setStep] = useState(0);
  const [f, setF] = useState<any>({ direction: "", specialization: "", primary_stack: "", industries: [], claimed_grade: "",
    years_experience: "", work_formats: [], salary_from: "", salary_to: "" });
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (prof?.specialization) setF((x: any) => ({ ...x, direction: prof.direction, specialization: prof.specialization,
      primary_stack: prof.primary_stack || "", industries: prof.industries || [], claimed_grade: prof.claimed_grade || "",
      years_experience: prof.years_experience ?? "", work_formats: prof.work_formats || [], salary_from: prof.salary_from || "", salary_to: prof.salary_to || "" }));
  }, [prof]);

  const directions = useMemo(() => Array.from(new Set(dict?.specializations.map((s) => s.direction) || [])), [dict]);
  if (!dict || !prof) return <Loading />;
  const specs = dict.specializations.filter((s) => s.direction === f.direction);
  const spec = dict.specializations.find((s) => s.slug === f.specialization);
  const canNext = [!!f.direction, !!f.specialization, true, !!f.claimed_grade, true][step];
  const locked = !!prof.category?.grade;

  async function finish() {
    setBusy(true);
    setErr(null);
    try {
      const r = await api<any>("/candidate/survey", { body: {
        ...f, years_experience: f.years_experience === "" ? null : Number(f.years_experience),
        salary_from: f.salary_from ? Number(f.salary_from) : null, salary_to: f.salary_to ? Number(f.salary_to) : null,
        primary_stack: f.primary_stack || null } });
      router.push(`/candidate/test?grade=${r.recommended_test_grade}`);
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }

  const card = (active: boolean) => clsx("w-full rounded-xl border-2 p-4 text-left transition-colors",
    active ? "border-plum bg-plum-50" : "border-mist-300 bg-white hover:border-plum/40");

  return (
    <>
      <PageHead title="Опрос по специализации" sub="Ответы определяют, какой тест вы пройдёте. Категорию работодатели увидят только по результату теста." />
      <ol className="mb-6 flex flex-wrap gap-2" aria-label="Шаги опроса">
        {STEPS.map((s, i) => (
          <li key={s} className={clsx("rounded-full px-3 py-1 text-sm font-semibold",
            i === step ? "bg-plum text-white" : i < step ? "bg-plum-100 text-plum" : "bg-mist text-ink/55")}>{i + 1}. {s}</li>
        ))}
      </ol>
      <Panel>
        {step === 0 && (
          <div className="grid gap-3 sm:grid-cols-2">
            {directions.map((d) => (
              <button key={d} className={card(f.direction === d)} disabled={locked}
                      onClick={() => setF({ ...f, direction: d, specialization: d === f.direction ? f.specialization : "" })}>
                <div className="font-bold text-plum">{d}</div>
                <div className="mt-1 text-sm text-ink/60">{dict.specializations.filter((s) => s.direction === d).map((s) => s.name).join(", ")}</div>
              </button>
            ))}
          </div>
        )}
        {step === 1 && (
          <div className="space-y-6">
            <div className="grid gap-3 sm:grid-cols-2">
              {specs.map((s) => (
                <button key={s.slug} className={card(f.specialization === s.slug)} disabled={locked}
                        onClick={() => setF({ ...f, specialization: s.slug, primary_stack: s.stacks[0] || "" })}>
                  <div className="font-bold text-plum">{s.name}</div>
                  <div className="mt-1 text-sm text-ink/60">{s.description}</div>
                </button>
              ))}
            </div>
            {locked && <p className="text-sm text-ink/60">Специализация закреплена категорией. Сменить её можно через поддержку и повторный тест.</p>}
            {spec && spec.stacks.length > 1 && (
              <Field label="Основной язык">
                <MultiPick options={spec.stacks.map((s) => ({ value: s, label: dict.skills.find((x) => x.slug === s)?.name || s }))}
                           value={f.primary_stack ? [f.primary_stack] : []} onChange={(v) => setF({ ...f, primary_stack: v[v.length - 1] || "" })} />
              </Field>
            )}
          </div>
        )}
        {step === 2 && (
          <Field label="В каких отраслях есть опыт или интерес?" hint="Необязательно. Помогает работодателям из этих отраслей.">
            <MultiPick options={dict.industries.map((i) => ({ value: i.slug, label: i.name }))} value={f.industries}
                       onChange={(v) => setF({ ...f, industries: v })} />
          </Field>
        )}
        {step === 3 && (
          <div className="space-y-5">
            <p className="text-[15px] text-ink/70">На какой грейд вы претендуете? Тест проверит именно этот уровень. Не прошли — сможете сразу пройти тест на уровень ниже; справились уверенно — система предложит попробовать уровень выше.</p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {dict.grades.map((g) => (
                <button key={g.slug} className={card(f.claimed_grade === g.slug)} onClick={() => setF({ ...f, claimed_grade: g.slug })}>
                  <div className="text-lg font-extrabold text-plum">{g.name}</div>
                  <div className="mt-1 text-sm text-ink/60">{g.experience}</div>
                </button>
              ))}
            </div>
            <Field label="Коммерческий опыт, лет" className="max-w-xs">
              <input className="input" type="number" min={0} max={60} step={0.5} value={f.years_experience} onChange={(e) => setF({ ...f, years_experience: e.target.value })} />
            </Field>
          </div>
        )}
        {step === 4 && (
          <div className="space-y-5">
            <Field label="Формат работы">
              <MultiPick options={dict.work_formats.map((w) => ({ value: w.slug, label: w.name }))} value={f.work_formats}
                         onChange={(v) => setF({ ...f, work_formats: v })} />
            </Field>
            <div className="grid max-w-lg gap-4 sm:grid-cols-2">
              <Field label="Зарплата от, ₽ в месяц"><input className="input" type="number" min={0} step={5000} value={f.salary_from} onChange={(e) => setF({ ...f, salary_from: e.target.value })} /></Field>
              <Field label="до, ₽ в месяц"><input className="input" type="number" min={0} step={5000} value={f.salary_to} onChange={(e) => setF({ ...f, salary_to: e.target.value })} /></Field>
            </div>
            <p className="text-sm text-ink/55">Работодатели увидят ваши ожидания, если вы не скроете их в настройках приватности. В каждом приглашении вилка указывается обязательно.</p>
          </div>
        )}
        <ErrorNote error={err} />
        <div className="mt-8 flex justify-between gap-3">
          <Button variant="ghost" onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0}>Назад</Button>
          {step < STEPS.length - 1
            ? <Button onClick={() => setStep(step + 1)} disabled={!canNext}>Дальше</Button>
            : <Button onClick={finish} loading={busy}>Сохранить и перейти к тесту</Button>}
        </div>
      </Panel>
    </>
  );
}
