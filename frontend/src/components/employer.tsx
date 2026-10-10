"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useDict } from "@/lib/session";
import type { CandidateCard, Need } from "@/lib/types";
import { Button, Chip, ErrorNote, Field, Modal, MultiPick } from "./ui";

export type NeedDraft = Omit<Need, "id" | "status" | "created_at"> & { id?: number };

export const emptyNeed: NeedDraft = {
  title: "", description: "", specialization: "backend", grades: ["middle"], must_skills: [], nice_skills: [], work_formats: [],
  city: "", salary_from: null, salary_to: null, allow_adjacent: false, parsed_by: "manual",
};

/** Текст потребности → структура (LLM или правила) → правка человеком. */
export function NeedParser({ onParsed }: { onParsed: (n: NeedDraft) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  async function parse() {
    setBusy(true);
    setErr(null);
    try {
      const r = await api<any>("/employer/needs/parse", { body: { text } });
      onParsed({ ...emptyNeed, ...r, description: text, city: r.city || "" });
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }
  return (
    <div>
      <Field label="Опишите своими словами, кто нужен" hint="Стек, задачи команды, грейд, формат, вилка. Например: «Нужен middle Python-разработчик в платёжный сервис: SQL, Docker, будет плюсом Kafka. 250–340 тыс., удалённо».">
        <textarea className="input min-h-32" value={text} onChange={(e) => setText(e.target.value)} />
      </Field>
      <ErrorNote error={err} />
      <div className="mt-3 flex flex-wrap gap-3">
        <Button onClick={parse} loading={busy} disabled={text.trim().length < 10}>Разобрать в требования</Button>
        <Button variant="ghost" onClick={() => onParsed({ ...emptyNeed })}>Заполнить вручную</Button>
      </div>
    </div>
  );
}

export function NeedForm({ value, onChange }: { value: NeedDraft; onChange: (n: NeedDraft) => void }) {
  const { dict } = useDict();
  if (!dict) return null;
  const spec = dict.specializations.find((s) => s.slug === value.specialization);
  const skillOpts = (pool: string[]) => dict.skills.filter((s) => pool.includes(s.slug)).map((s) => ({ value: s.slug, label: s.name }));
  const others = dict.skills.map((s) => s.slug).filter((s) => !spec?.core_skills.includes(s));
  const set = (patch: Partial<NeedDraft>) => onChange({ ...value, ...patch });
  return (
    <div className="space-y-5">
      {value.parsed_by !== "manual" && (
        <p className="rounded-lg bg-plum-50 px-4 py-2.5 text-sm text-plum">
          Требования извлечены из текста {value.parsed_by === "llm" ? "языковой моделью" : "по правилам"} — проверьте и поправьте при необходимости.
        </p>
      )}
      <Field label="Название подборки"><input className="input" value={value.title} onChange={(e) => set({ title: e.target.value })} /></Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Специализация">
          <select className="input" value={value.specialization} onChange={(e) => set({ specialization: e.target.value })}>
            {dict.specializations.map((s) => <option key={s.slug} value={s.slug}>{s.name}</option>)}
          </select>
        </Field>
        <Field label="Грейд">
          <MultiPick options={dict.grades.map((g) => ({ value: g.slug, label: g.name }))} value={value.grades} onChange={(v) => set({ grades: v })} />
        </Field>
      </div>
      <Field label="Обязательные навыки" hint="Кандидаты без подтверждения этих навыков опустятся в выдаче">
        <MultiPick options={[...skillOpts(spec?.core_skills || []), ...skillOpts(others)]} value={value.must_skills}
                   onChange={(v) => set({ must_skills: v, nice_skills: value.nice_skills.filter((x) => !v.includes(x)) })} />
      </Field>
      <Field label="Будет плюсом">
        <MultiPick options={[...skillOpts(spec?.core_skills || []), ...skillOpts(others)].filter((o) => !value.must_skills.includes(o.value))}
                   value={value.nice_skills} onChange={(v) => set({ nice_skills: v })} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Вилка от, ₽"><input className="input" type="number" step={5000} value={value.salary_from ?? ""} onChange={(e) => set({ salary_from: e.target.value ? Number(e.target.value) : null })} /></Field>
        <Field label="до, ₽"><input className="input" type="number" step={5000} value={value.salary_to ?? ""} onChange={(e) => set({ salary_to: e.target.value ? Number(e.target.value) : null })} /></Field>
        <Field label="Город"><input className="input" value={value.city || ""} onChange={(e) => set({ city: e.target.value })} /></Field>
      </div>
      <Field label="Формат работы">
        <MultiPick options={dict.work_formats.map((w) => ({ value: w.slug, label: w.name }))} value={value.work_formats} onChange={(v) => set({ work_formats: v })} />
      </Field>
      <label className="flex items-start gap-3 text-sm">
        <input type="checkbox" className="mt-1 h-4 w-4 accent-plum" checked={value.allow_adjacent} onChange={(e) => set({ allow_adjacent: e.target.checked })} />
        <span>Показывать и смежные категории: соседний грейд и близкие специализации (с пониженным весом)</span>
      </label>
    </div>
  );
}

export function needPayload(n: NeedDraft) {
  return {
    title: n.title || "Подборка", description: n.description || "", specialization: n.specialization, grades: n.grades.length ? n.grades : ["middle"],
    must_skills: n.must_skills, nice_skills: n.nice_skills, work_formats: n.work_formats, city: n.city || null,
    salary_from: n.salary_from || null, salary_to: n.salary_to || null, allow_adjacent: n.allow_adjacent, parsed_by: n.parsed_by || "manual",
  };
}

/** Приглашение: обязательны описание, вилка и способ связи. */
export function InviteModal({ candidate, need, open, onClose, onSent, defaultContact }: {
  candidate: Pick<CandidateCard, "id" | "name" | "category" | "salary_from" | "salary_to">; need?: Need | null; open: boolean;
  onClose: () => void; onSent: () => void; defaultContact?: string;
}) {
  const { dict } = useDict();
  const [f, setF] = useState({
    title: need?.title || "", description: need?.description || "", salary_from: need?.salary_from || "", salary_to: need?.salary_to || "",
    contact_method: defaultContact || "", work_format: need?.work_formats?.[0] || "",
  });
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function send() {
    setBusy(true);
    setErr(null);
    try {
      await api("/invitations", { body: { candidate_id: candidate.id, need_id: need?.id, title: f.title, description: f.description,
        salary_from: Number(f.salary_from), salary_to: Number(f.salary_to), contact_method: f.contact_method, work_format: f.work_format || null } });
      onSent();
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }
  const salaryNote = candidate.salary_from && f.salary_to && Number(f.salary_to) < candidate.salary_from
    ? `Ожидания кандидата — от ${Math.round(candidate.salary_from / 1000)} тыс. ₽, это выше вашей вилки.` : null;
  return (
    <Modal open={open} onClose={onClose} title={`Приглашение: ${candidate.name}`} wide>
      <div className="space-y-4">
        <p className="text-sm text-ink/60">{candidate.category.label}. Кандидат увидит компанию, предложение и вилку до начала общения. Контакты кандидата откроются, когда он примет приглашение.</p>
        <Field label="Позиция"><input className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
        <Field label="Предложение" hint="Чем предстоит заниматься, команда, условия"><textarea className="input min-h-28" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Зарплата от, ₽"><input className="input" type="number" step={5000} required value={f.salary_from} onChange={(e) => setF({ ...f, salary_from: e.target.value })} /></Field>
          <Field label="до, ₽"><input className="input" type="number" step={5000} required value={f.salary_to} onChange={(e) => setF({ ...f, salary_to: e.target.value })} /></Field>
          <Field label="Формат">
            <select className="input" value={f.work_format} onChange={(e) => setF({ ...f, work_format: e.target.value })}>
              <option value="">Обсуждается</option>{dict?.work_formats.map((w) => <option key={w.slug} value={w.slug}>{w.name}</option>)}
            </select>
          </Field>
        </div>
        {salaryNote && <Chip tone="warn">{salaryNote}</Chip>}
        <Field label="Как с вами связаться" hint="Email, телефон или Telegram рекрутера"><input className="input" value={f.contact_method} onChange={(e) => setF({ ...f, contact_method: e.target.value })} /></Field>
        <ErrorNote error={err} />
        <div className="flex justify-end gap-3">
          <Button variant="ghost" onClick={onClose}>Отмена</Button>
          <Button onClick={send} loading={busy} disabled={!f.title || f.description.length < 10 || !f.salary_from || !f.salary_to || f.contact_method.length < 3}>
            Отправить приглашение
          </Button>
        </div>
      </div>
    </Modal>
  );
}
