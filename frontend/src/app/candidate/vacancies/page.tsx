"use client";
import Link from "next/link";
import { useState } from "react";
import { Chip, Empty, Field, Loading, PageHead, StatusChip } from "@/components/ui";
import { qs, rubRange, useApi } from "@/lib/api";
import { useDict } from "@/lib/session";
import type { Vacancy } from "@/lib/types";

export default function Vacancies() {
  const { dict, formatName } = useDict();
  const [f, setF] = useState({ specialization: "", grade: "", q: "", work_format: "" });
  const { data } = useApi<{ total: number; items: Vacancy[] }>(`/vacancies${qs(f)}`);
  return (
    <>
      <PageHead title="Вакансии" sub="Основной путь — приглашения от работодателей, но откликнуться самостоятельно тоже можно. При отклике компания сразу увидит ваши контакты." />
      <div className="mb-6 grid gap-3 sm:grid-cols-4">
        <Field label="Поиск"><input className="input" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} placeholder="Python, платежи…" /></Field>
        <Field label="Специализация">
          <select className="input" value={f.specialization} onChange={(e) => setF({ ...f, specialization: e.target.value })}>
            <option value="">Любая</option>{dict?.specializations.map((s) => <option key={s.slug} value={s.slug}>{s.name}</option>)}
          </select>
        </Field>
        <Field label="Грейд">
          <select className="input" value={f.grade} onChange={(e) => setF({ ...f, grade: e.target.value })}>
            <option value="">Любой</option>{dict?.grades.map((g) => <option key={g.slug} value={g.slug}>{g.name}</option>)}
          </select>
        </Field>
        <Field label="Формат">
          <select className="input" value={f.work_format} onChange={(e) => setF({ ...f, work_format: e.target.value })}>
            <option value="">Любой</option>{dict?.work_formats.map((g) => <option key={g.slug} value={g.slug}>{g.name}</option>)}
          </select>
        </Field>
      </div>
      {!data ? <Loading /> : data.items.length === 0 ? <Empty title="Вакансий по фильтрам нет" text="Измените фильтры или дождитесь приглашений." /> : (
        <div className="space-y-3">
          {data.items.map((v) => (
            <Link key={v.id} href={`/candidate/vacancies/${v.id}`} className="panel block p-5 hover:border-plum/40">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-lg font-bold text-plum">{v.title}</div>
                  <div className="text-[15px] text-ink/70">{v.company.name}, {v.city || "город не указан"}, {formatName(v.work_format).toLowerCase()}</div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <Chip tone="mist">{v.specialization_name}, {v.grade_name}</Chip>
                    {v.match?.same_category && <Chip tone="ok">ваша категория</Chip>}
                    {v.my_application && <StatusChip status={v.my_application} />}
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-extrabold text-plum">{rubRange(v.salary_from, v.salary_to)}</div>
                  {v.match && <div className="mt-1 text-sm text-ink/60">соответствие {Math.round(v.match.score)} из 100</div>}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
