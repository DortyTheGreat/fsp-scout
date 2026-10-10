"use client";
import { useEffect, useState } from "react";
import { Button, ErrorNote, Field, Loading, PageHead, Panel, useToast } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { useDict } from "@/lib/session";

export default function Company() {
  const { data, mutate } = useApi<any>("/employer/company");
  const { dict } = useDict();
  const [f, setF] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  useEffect(() => { if (data && !f) setF(Object.fromEntries(Object.entries(data).map(([k, v]) => [k, v ?? ""]))); }, [data, f]);
  if (!f) return <Loading />;
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const { id, ...body } = f;
      await mutate(await api("/employer/company", { method: "PUT", body: Object.fromEntries(Object.entries(body).map(([k, v]) => [k, v === "" ? null : v])) }), { revalidate: false });
      toast.show("Профиль компании сохранён");
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }
  return (
    <>
      <PageHead title="Компания" sub="Название, описание и контакты видит кандидат в каждом приглашении." />
      {toast.node}
      <form onSubmit={save}>
        <Panel>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Название"><input className="input" required value={f.name} onChange={set("name")} /></Field>
            <Field label="Отрасль">
              <select className="input" value={f.industry} onChange={set("industry")}>
                <option value="">Не указана</option>{dict?.industries.map((i) => <option key={i.slug} value={i.slug}>{i.name}</option>)}
              </select>
            </Field>
            <Field label="Чем занимается компания" className="sm:col-span-2"><textarea className="input min-h-28" value={f.description} onChange={set("description")} /></Field>
            <Field label="Сайт"><input className="input" value={f.website} onChange={set("website")} /></Field>
            <Field label="Город"><input className="input" value={f.city} onChange={set("city")} /></Field>
            <Field label="Размер"><input className="input" value={f.size} onChange={set("size")} placeholder="например, 50–200" /></Field>
            <Field label="Контактное лицо"><input className="input" value={f.contact_name} onChange={set("contact_name")} /></Field>
            <Field label="Email для кандидатов"><input className="input" type="email" value={f.contact_email} onChange={set("contact_email")} /></Field>
            <Field label="Telegram"><input className="input" value={f.contact_telegram} onChange={set("contact_telegram")} /></Field>
          </div>
          <ErrorNote error={err} />
          <Button type="submit" className="mt-6" loading={busy}>Сохранить</Button>
        </Panel>
      </form>
    </>
  );
}
