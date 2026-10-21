"use client";
import { useEffect, useRef, useState } from "react";
import { FspBlock, SkillList } from "@/components/domain";
import { Button, Chip, ErrorNote, Field, Loading, MultiPick, PageHead, Panel, Spinner, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { useDict } from "@/lib/session";

const FIELD_NAMES: Record<string, string> = {
  full_name: "ФИО", email: "Email", phone: "Телефон", telegram: "Telegram", city: "Город", years_experience: "Стаж",
  grade: "Грейд (по резюме)", specialization: "Специализация", skills: "Стек", roles: "Роли", soft_skills: "Софт-скиллы",
};

const llmPending = (x: any) => x?.resume_parse_meta?.llm_status === "pending";

export default function Profile() {
  // пока локальная модель уточняет черновик резюме (фоном, до минуты), профиль перечитывается каждые 4 с
  const { data: p, mutate } = useApi<any>("/candidate/profile", { refreshInterval: (d) => (llmPending(d) ? 4000 : 0) });
  const { dict, skillName, gradeName, specName } = useDict();
  const [f, setF] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [parsed, setParsed] = useState<any>(null);
  const [upBusy, setUpBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [refineNote, setRefineNote] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const prevStatus = useRef<string | undefined>(undefined);
  const toast = useToast();

  useEffect(() => {
    if (p && !f) setF({ full_name: p.full_name || "", phone: p.phone || "", telegram: p.telegram || "", contact_email: p.contact_email || "",
      city: p.city || "", about: p.about || "", years_experience: p.years_experience ?? "", claimed_skills: p.claimed_skills || [],
      soft_skills: p.soft_skills || [], salary_from: p.salary_from || "", salary_to: p.salary_to || "", work_formats: p.work_formats || [],
      relocation: !!p.relocation, education: p.education || "",
      experience: (p.experience || []).map((e: any) => ({ company: e.company || "", position: e.position || "", period: e.period || "", description: e.description || "" })) });
  }, [p, f]);

  // модель закончила уточнять черновик: обновляем форму, если кандидат её ещё не правил
  const status = p?.resume_parse_meta?.llm_status;
  useEffect(() => {
    if (prevStatus.current === "pending" && status && status !== "pending") {
      const meta = p.resume_parse_meta;
      if (status === "done") {
        setParsed({ parsed: meta.parsed || {}, meta });
        const n = (meta.updated || []).length;
        if (!dirty) { setF(null); setRefineNote(n ? `Модель уточнила черновик: обновлено полей — ${n}. Проверьте и сохраните.` : "Модель проверила черновик: менять нечего."); }
        else setRefineNote("Модель уточнила черновик. Чтобы увидеть её вариант, сохраните свои правки и обновите страницу.");
      } else setRefineNote("Модель не ответила — остался разбор по правилам.");
    }
    prevStatus.current = status;
  }, [status]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!p || !f || !dict) return <Loading />;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const body = { ...f, years_experience: f.years_experience === "" ? null : Number(f.years_experience),
        salary_from: f.salary_from ? Number(f.salary_from) : null, salary_to: f.salary_to ? Number(f.salary_to) : null,
        experience: f.experience.filter((e: any) => e.company.trim() || e.position.trim()) };
      await mutate(await api("/candidate/profile", { method: "PUT", body }), { revalidate: false });
      setDirty(false);
      toast.show("Профиль сохранён");
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }

  async function upload(file: File) {
    setUpBusy(true);
    setErr(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await api<any>("/candidate/resume?apply=true", { form });
      setParsed(r);
      setRefineNote(null);
      setDirty(false);
      setF(null);
      prevStatus.current = r.meta?.llm_status;
      await mutate(r.profile, { revalidate: false });
    } catch (e) { setErr(e); } finally { setUpBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  }

  const upd = (patch: Record<string, unknown>) => { setF({ ...f, ...patch }); setDirty(true); };
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => upd({ [k]: e.target.value });
  const setJob = (i: number, k: string, v: string) => upd({ experience: f.experience.map((e: any, j: number) => (j === i ? { ...e, [k]: v } : e)) });
  const addJob = () => upd({ experience: [...f.experience, { company: "", position: "", period: "", description: "" }] });
  const delJob = (i: number) => upd({ experience: f.experience.filter((_: any, j: number) => j !== i) });
  const pending = llmPending(p);
  const skillGroups = Array.from(new Set(dict.skills.map((s) => s.group)));

  return (
    <>
      <PageHead title="Профиль и резюме" sub="Резюме помогает работодателю узнать вас, но на категорию не влияет — её определяет тест."
                action={<Button variant="secondary" href="/api/v1/candidate/profile.pdf">Скачать PDF-профиль</Button>} />
      {toast.node}
      <Panel title="Загрузить резюме в PDF" className="mb-6">
        <p className="text-[15px] text-ink/70">Распознаем ФИО, контакты, места работы, стек, стаж, роли и софт-скиллы и заполним пустые поля анкеты. Проверьте результат перед сохранением.</p>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <input ref={fileRef} type="file" accept="application/pdf" className="hidden" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          <Button variant="plum" loading={upBusy} onClick={() => fileRef.current?.click()}>Выбрать PDF</Button>
          {p.resume_parse_meta?.method && <span className="text-sm text-ink/55">Последний разбор: {p.resume_parse_meta.method === "rules" ? "по правилам" : "LLM и правила"}</span>}
        </div>
        {pending && (
          <div className="mt-4 flex items-center gap-2 text-sm text-plum" role="status">
            <Spinner small /> Локальная модель уточняет черновик — обычно до минуты. Поля обновятся сами, правки не потеряются.
          </div>
        )}
        {refineNote && !pending && <div className="mt-4 text-sm text-ink/70" role="status">{refineNote}</div>}
        {parsed && (
          <div className="mt-5 rounded-xl bg-mist-50 p-4">
            <div className="mb-2 font-semibold text-plum">Что удалось распознать</div>
            <dl className="grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
              {Object.entries(FIELD_NAMES).map(([k, label]) => {
                const v = parsed.parsed[k];
                const shown = Array.isArray(v) ? (k === "skills" ? v.map(skillName) : k === "roles" ? v.map((r: string) => dict.roles.find((x) => x.slug === r)?.name || r) : v).join(", ") : k === "grade" ? gradeName(v) : k === "specialization" ? specName(v) : v;
                return (
                  <div key={k} className="flex gap-2">
                    <dt className="w-32 shrink-0 text-ink/55">{label}</dt>
                    <dd className="font-medium">{shown || <span className="text-ink/40">не найдено</span>}
                      {parsed.meta.fields?.[k] === "llm" && <Chip tone="lavender" className="ml-1.5 !text-[10px]">LLM</Chip>}</dd>
                  </div>
                );
              })}
            </dl>
            <div className="mt-3 text-sm">
              <div className="mb-1 flex items-center gap-1.5 text-ink/55">Места работы
                {parsed.meta.fields?.experience === "llm" && <Chip tone="lavender" className="!text-[10px]">LLM</Chip>}</div>
              {(parsed.parsed.experience || []).length ? (
                <ul className="space-y-0.5">
                  {parsed.parsed.experience.map((e: any, i: number) => (
                    <li key={i}><b>{e.position || "должность не распознана"}</b>{e.company ? `, ${e.company}` : ""}<span className="text-ink/55">{e.period ? ` · ${e.period}` : ""}</span></li>
                  ))}
                </ul>
              ) : <span className="text-ink/40">не найдено</span>}
              {(parsed.parsed.experience || []).length > 0 && JSON.stringify(parsed.parsed.experience.map((e: any) => [e.company, e.position]))
                !== JSON.stringify(f.experience.map((e: any) => [e.company, e.position])) && (
                <Button type="button" variant="secondary" size="sm" className="mt-2"
                        onClick={() => upd({ experience: parsed.parsed.experience.map((e: any) => ({ company: e.company || "", position: e.position || "",
                          period: e.period || "", description: e.description || "" })) })}>
                  Подставить места работы из резюме
                </Button>
              )}
            </div>
          </div>
        )}
      </Panel>

      <form onSubmit={save} className="grid gap-6 lg:grid-cols-2">
        <Panel title="Контакты" >
          <p className="mb-4 text-sm text-ink/60">Работодатель увидит их, только если вы примете его приглашение или сами откликнетесь.</p>
          <div className="grid gap-4">
            <Field label="Фамилия и имя"><input className="input" value={f.full_name} onChange={set("full_name")} /></Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Телефон"><input className="input" value={f.phone} onChange={set("phone")} autoComplete="tel" /></Field>
              <Field label="Telegram"><input className="input" value={f.telegram} onChange={set("telegram")} placeholder="@username" /></Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Email для связи"><input className="input" type="email" value={f.contact_email} onChange={set("contact_email")} /></Field>
              <Field label="Город"><input className="input" value={f.city} onChange={set("city")} /></Field>
            </div>
          </div>
        </Panel>
        <Panel title="Условия">
          <div className="grid gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Зарплата от, ₽"><input className="input" type="number" step={5000} value={f.salary_from} onChange={set("salary_from")} /></Field>
              <Field label="до, ₽"><input className="input" type="number" step={5000} value={f.salary_to} onChange={set("salary_to")} /></Field>
            </div>
            <Field label="Формат работы">
              <MultiPick options={dict.work_formats.map((w) => ({ value: w.slug, label: w.name }))} value={f.work_formats} onChange={(v) => upd({ work_formats: v })} />
            </Field>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-plum" checked={f.relocation} onChange={(e) => upd({ relocation: e.target.checked })} />Готов к переезду</label>
            <Field label="Коммерческий опыт, лет"><input className="input max-w-[10rem]" type="number" step={0.5} value={f.years_experience} onChange={set("years_experience")} /></Field>
          </div>
        </Panel>
        <Panel title="Опыт работы" className="lg:col-span-2"
               action={<Button type="button" variant="ghost" size="sm" onClick={addJob}>+ Место работы</Button>}>
          <p className="mb-4 text-sm text-ink/60">Заполняется из PDF-резюме — проверьте компанию, должность и период. Работодатель видит опыт, если это разрешено в настройках приватности.</p>
          {f.experience.length === 0 ? (
            <p className="text-sm text-ink/50">Мест работы пока нет. Загрузите резюме или добавьте вручную.</p>
          ) : (
            <div className="space-y-4">
              {f.experience.map((e: any, i: number) => (
                <div key={i} className="rounded-xl border border-mist-300 p-4">
                  <div className="grid gap-3 sm:grid-cols-3">
                    <Field label="Компания"><input className="input" value={e.company} onChange={(ev) => setJob(i, "company", ev.target.value)} /></Field>
                    <Field label="Должность"><input className="input" value={e.position} onChange={(ev) => setJob(i, "position", ev.target.value)} /></Field>
                    <Field label="Период"><input className="input" value={e.period} placeholder="03.2021 — настоящее время" onChange={(ev) => setJob(i, "period", ev.target.value)} /></Field>
                  </div>
                  <Field label="Чем занимались" className="mt-3"><textarea className="input min-h-20" value={e.description} onChange={(ev) => setJob(i, "description", ev.target.value)} /></Field>
                  <Button type="button" variant="ghost" size="sm" className="mt-2" onClick={() => delJob(i)}>Удалить</Button>
                </div>
              ))}
            </div>
          )}
        </Panel>
        <Panel title="О себе" className="lg:col-span-2">
          <div className="grid gap-4">
            <Field label="Коротко о себе и опыте"><textarea className="input min-h-28" value={f.about} onChange={set("about")} /></Field>
            <Field label="Образование"><input className="input" value={f.education} onChange={set("education")} /></Field>
            <div>
              <span className="label">Стек, с которым работали</span>
              <p className="hint mb-3">Отмеченное, но не проверенное тестом, работодатель видит с пометкой «заявлено».</p>
              <div className="space-y-3">
                {skillGroups.map((g) => (
                  <div key={g}>
                    <div className="mb-1.5 text-xs font-semibold text-ink/50">{g}</div>
                    <MultiPick options={dict.skills.filter((s) => s.group === g).map((s) => ({ value: s.slug, label: s.name }))}
                               value={f.claimed_skills} onChange={(v) => upd({ claimed_skills: v })} />
                  </div>
                ))}
              </div>
            </div>
            <Field label="Софт-скиллы">
              <MultiPick options={dict.soft_skills.map((s) => ({ value: s, label: s }))} value={f.soft_skills} onChange={(v) => upd({ soft_skills: v })} />
            </Field>
          </div>
          <ErrorNote error={err} />
          <Button type="submit" className="mt-6" loading={busy}>Сохранить профиль</Button>
        </Panel>
      </form>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Panel title="Навыки, подтверждённые тестом"><SkillList skills={p.skills} /></Panel>
        <Panel title="Достижения ФСП"><FspBlock fsp={p.fsp} compact own /></Panel>
      </div>
    </>
  );
}
