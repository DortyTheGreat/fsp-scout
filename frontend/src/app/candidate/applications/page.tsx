"use client";
import Link from "next/link";
import { Button, Empty, Loading, PageHead, StatusChip } from "@/components/ui";
import { api, dateRu, rubRange, useApi } from "@/lib/api";

export default function Applications() {
  const { data, mutate } = useApi<any[]>("/applications");
  if (!data) return <Loading />;
  return (
    <>
      <PageHead title="Мои отклики" sub="Статусы обновляются, когда компания открывает отклик и принимает решение." />
      {data.length === 0 ? <Empty title="Вы ещё не откликались" action={<Button href="/candidate/vacancies" variant="secondary">Посмотреть вакансии</Button>} /> : (
        <div className="panel divide-y divide-mist">
          {data.map((a) => (
            <div key={a.id} className="flex flex-wrap items-center gap-4 px-5 py-4">
              <div className="min-w-0 flex-1">
                <Link href={`/candidate/vacancies/${a.vacancy.id}`} className="font-bold text-plum hover:underline">{a.vacancy.title}</Link>
                <div className="text-sm text-ink/60">{a.vacancy.company}, {rubRange(a.vacancy.salary_from, a.vacancy.salary_to)}, отклик {dateRu(a.created_at)}</div>
                {a.employer_comment && <div className="mt-1 text-sm">Комментарий компании: {a.employer_comment}</div>}
              </div>
              <StatusChip status={a.status} />
              {(a.status === "sent" || a.status === "viewed") && (
                <button className="text-sm font-semibold text-ink/55 underline" onClick={async () => { await api(`/applications/${a.id}/withdraw`, { method: "POST" }); mutate(); }}>Отозвать</button>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
