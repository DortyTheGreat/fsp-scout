"use client";
import { useState } from "react";
import { Prompt } from "@/components/domain";
import { Button, Chip, ErrorNote, Field, Loading, Modal, PageHead, Panel, StatusChip, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { useDict } from "@/lib/session";

function Preview({ id, onClose }: { id: string; onClose: () => void }) {
  const [seed, setSeed] = useState<number | null>(null);
  const { data } = useApi<any>(`/admin/items/${id}/preview${seed !== null ? `?seed=${seed}` : ""}`);
  const correct = data ? (data.fmt === "single" ? data.options?.[data.answer] : data.fmt === "multi" ? data.answer.map((i: number) => data.options[i]).join("; ") : data.answer.join(" или ")) : "";
  return (
    <Modal open onClose={onClose} title={`Шаблон ${id}`} wide>
      {!data ? <Loading /> : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3 text-sm text-ink/60">seed {data.seed}
            <Button size="sm" variant="secondary" onClick={() => setSeed(Math.floor(Math.random() * 2 ** 31))}>Другой экземпляр</Button></div>
          <Prompt text={data.prompt} />
          {data.code && <pre className="code-block">{data.code}</pre>}
          {data.options && <ul className="list-disc pl-5 text-sm">{data.options.map((o: string, i: number) => <li key={i}>{o}</li>)}</ul>}
          <div className="rounded-xl bg-emerald-50 p-3 text-sm"><b>Ответ:</b> {correct}{data.explanation ? `. ${data.explanation}` : ""}</div>
        </div>
      )}
    </Modal>
  );
}

export default function Items() {
  const { data, mutate } = useApi<any[]>("/admin/items");
  const { dict, specName } = useDict();
  const [spec, setSpec] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const [draft, setDraft] = useState({ specialization: "backend", skill: "python", level: "middle", context: "" });
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [calib, setCalib] = useState<any[] | null>(null);
  const toast = useToast();
  if (!data || !dict) return <Loading />;
  const rows = data.filter((r) => !spec || r.specializations.includes(spec));

  async function makeDraft() {
    setBusy(true);
    setErr(null);
    try { await api("/admin/items/draft", { body: draft }); toast.show("Черновик добавлен в банк со статусом «черновик»"); mutate(); }
    catch (e) { setErr(e); } finally { setBusy(false); }
  }
  async function status(id: string, s: string) {
    try { await api(`/admin/items/${id}/status`, { body: { status: s } }); mutate(); } catch (e) { toast.show((e as Error).message); }
  }

  return (
    <>
      <PageHead title="Банк заданий" sub="Параметрические шаблоны с параметрами IRT: a — дискриминативность, b — трудность, c — угадывание. «Вариантов» — сколько различных экземпляров дали 200 случайных seed."
                action={<Button variant="secondary" onClick={async () => setCalib(await api("/admin/items/calibrate", { method: "POST" }))}>Откалибровать претест-задания</Button>} />
      {toast.node}
      {calib && (
        <Panel className="mb-6" title="Результат калибровки">
          {calib.length === 0 ? <p className="text-sm">Претест-заданий нет.</p> : calib.map((c) => <div key={c.id} className="text-sm">{c.id}: n={c.n}, {c.a !== undefined ? `a=${c.a}, b=${c.b}, ` : ""}{c.status}</div>)}
        </Panel>
      )}
      <Panel className="mb-6" title="Новое задание от LLM">
        <p className="mb-4 text-sm text-ink/65">LLM предлагает черновик под навык и контекст вакансии. Путь в рабочий банк: черновик → ревью эксперта → претест (незачётные показы в реальных тестах) → калибровка → рабочий.</p>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Специализация"><select className="input" value={draft.specialization} onChange={(e) => setDraft({ ...draft, specialization: e.target.value })}>{dict.specializations.map((s) => <option key={s.slug} value={s.slug}>{s.name}</option>)}</select></Field>
          <Field label="Навык"><select className="input" value={draft.skill} onChange={(e) => setDraft({ ...draft, skill: e.target.value })}>{dict.skills.map((s) => <option key={s.slug} value={s.slug}>{s.name}</option>)}</select></Field>
          <Field label="Уровень"><select className="input" value={draft.level} onChange={(e) => setDraft({ ...draft, level: e.target.value })}>{["junior", "middle", "senior"].map((l) => <option key={l}>{l}</option>)}</select></Field>
          <Field label="Контекст вакансии" className="sm:col-span-3"><textarea className="input" value={draft.context} onChange={(e) => setDraft({ ...draft, context: e.target.value })} /></Field>
        </div>
        <ErrorNote error={err} />
        <Button className="mt-4" onClick={makeDraft} loading={busy}>Сгенерировать черновик</Button>
      </Panel>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select className="input max-w-xs" value={spec} onChange={(e) => setSpec(e.target.value)} aria-label="Фильтр по специализации">
          <option value="">Все специализации ({data.length})</option>{dict.specializations.map((s) => <option key={s.slug} value={s.slug}>{s.name}</option>)}
        </select>
      </div>
      <div className="panel overflow-x-auto">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead><tr className="border-b border-mist text-ink/55">
            {["Шаблон", "Навыки", "Уровень", "a", "b", "c", "Показов", "Доля верных", "Вариантов", "Статус", ""].map((h) => <th key={h} className="px-3 py-2.5 font-semibold">{h}</th>)}
          </tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-mist last:border-0 hover:bg-mist-50">
                <td className="px-3 py-2"><button className="text-left font-semibold text-plum hover:underline" onClick={() => setPreview(r.id)}>{r.title}</button>
                  <div className="text-2xs text-ink/45">{r.id}; {r.specializations.map(specName).join(", ")}</div></td>
                <td className="px-3 py-2">{Object.keys(r.skills).join(", ")}</td>
                <td className="px-3 py-2">{r.level}</td>
                <td className="px-3 py-2 tabular-nums">{r.a}</td>
                <td className="px-3 py-2 tabular-nums">{r.b}</td>
                <td className="px-3 py-2 tabular-nums">{r.c}</td>
                <td className="px-3 py-2 tabular-nums">{r.exposure_count}</td>
                <td className="px-3 py-2 tabular-nums">{r.p_correct ?? "—"}</td>
                <td className="px-3 py-2 tabular-nums">{r.variant_space >= 200 ? "200+" : r.variant_space}</td>
                <td className="px-3 py-2">{r.source === "llm" ? <Chip tone="lavender">LLM</Chip> : null} <StatusChip status={r.status === "pretest" ? "in_progress" : r.status} /></td>
                <td className="px-3 py-2">
                  {r.status === "draft" && <Button size="sm" variant="secondary" onClick={() => status(r.id, "pretest")}>В претест</Button>}
                  {r.status === "active" && <button className="text-xs text-ink/50 underline" onClick={() => status(r.id, "retired")}>Вывести</button>}
                  {r.status === "retired" && <button className="text-xs text-ink/50 underline" onClick={() => status(r.id, "active")}>Вернуть</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {preview && <Preview id={preview} onClose={() => setPreview(null)} />}
    </>
  );
}
