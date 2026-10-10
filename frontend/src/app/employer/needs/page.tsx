"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { NeedDraft, NeedForm, NeedParser, needPayload } from "@/components/employer";
import { SkillNames } from "@/components/domain";
import { Button, Empty, ErrorNote, Loading, PageHead, Panel, StatusChip } from "@/components/ui";
import { api, dateRu, rubRange, useApi } from "@/lib/api";
import { useDict } from "@/lib/session";
import type { Need } from "@/lib/types";

function Needs() {
  const sp = useSearchParams();
  const router = useRouter();
  const { data } = useApi<Need[]>("/employer/needs");
  const { specName, gradeName } = useDict();
  const [creating, setCreating] = useState(sp.get("new") === "1");
  const [draft, setDraft] = useState<NeedDraft | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (!data) return <Loading />;

  async function create() {
    setBusy(true);
    setErr(null);
    try {
      const n = await api<Need>("/employer/needs", { body: needPayload(draft!) });
      router.push(`/employer/needs/${n.id}`);
    } catch (e) { setErr(e); setBusy(false); }
  }

  return (
    <>
      <PageHead title="Подборки" sub="Подборка — это потребность: кого ищете и под какие задачи. На её основе система ранжирует кандидатов из подходящих категорий."
                action={!creating && <Button onClick={() => setCreating(true)}>Новая подборка</Button>} />
      {creating && (
        <Panel title="Новая подборка" className="mb-6">
          {!draft ? <NeedParser onParsed={setDraft} /> : (
            <>
              <NeedForm value={draft} onChange={setDraft} />
              <ErrorNote error={err} />
              <div className="mt-6 flex flex-wrap gap-3">
                <Button onClick={create} loading={busy}>Показать кандидатов</Button>
                <Button variant="ghost" onClick={() => setDraft(null)}>Вернуться к тексту</Button>
              </div>
            </>
          )}
        </Panel>
      )}
      {data.length === 0 && !creating ? <Empty title="Подборок пока нет" action={<Button onClick={() => setCreating(true)}>Создать подборку</Button>} /> : (
        <div className="space-y-3">
          {data.map((n) => (
            <Link key={n.id} href={`/employer/needs/${n.id}`} className="panel block p-5 hover:border-plum/40">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-lg font-bold text-plum">{n.title}</div>
                  <div className="text-sm text-ink/60">{specName(n.specialization)}, {n.grades.map(gradeName).join(" или ")}, {rubRange(n.salary_from, n.salary_to)}, создана {dateRu(n.created_at)}</div>
                </div>
                <StatusChip status={n.status} />
              </div>
              {n.must_skills.length > 0 && <div className="mt-3"><SkillNames slugs={n.must_skills} /></div>}
            </Link>
          ))}
        </div>
      )}
    </>
  );
}

export default function Page() {
  return <Suspense><Needs /></Suspense>;
}
