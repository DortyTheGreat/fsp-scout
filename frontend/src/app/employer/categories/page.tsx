"use client";
import Link from "next/link";
import { Loading, PageHead } from "@/components/ui";
import { useApi } from "@/lib/api";
import { useDict } from "@/lib/session";

export default function Categories() {
  const { data } = useApi<any[]>("/employer/categories");
  const { dict } = useDict();
  if (!data || !dict) return <Loading />;
  const grades = ["junior", "middle", "senior"];
  return (
    <>
      <PageHead title="Каталог категорий" sub="Категория — специализация и грейд, подтверждённые тестом. Цифры обновляются по мере того, как кандидаты проходят тестирование." />
      <div className="panel overflow-x-auto">
        <table className="w-full min-w-[640px] text-left">
          <thead>
            <tr className="border-b border-mist text-sm text-ink/55">
              <th className="px-5 py-3 font-semibold">Специализация</th>
              {grades.map((g) => <th key={g} className="px-5 py-3 font-semibold">{dict.grades.find((x) => x.slug === g)?.name}</th>)}
            </tr>
          </thead>
          <tbody>
            {dict.specializations.map((s) => (
              <tr key={s.slug} className="border-b border-mist last:border-0">
                <td className="px-5 py-4">
                  <div className="font-bold text-plum">{s.name}</div>
                  <div className="text-xs text-ink/55">{s.direction}</div>
                </td>
                {grades.map((g) => {
                  const c = data.find((x) => x.specialization === s.slug && x.grade === g);
                  return (
                    <td key={g} className="px-5 py-4 align-top">
                      {c && c.count > 0 ? (
                        <Link href={`/employer/search?specialization=${s.slug}&grade=${g}`} className="group block">
                          <span className="text-2xl font-extrabold tabular-nums text-plum group-hover:text-signal">{c.count}</span>
                          <span className="ml-1 text-sm text-ink/55">чел.</span>
                          <div className="text-xs text-ink/60">
                            {c.salary_median ? `медиана ${Math.round(c.salary_median / 1000)} тыс. ₽` : ""}{c.salary_p25 ? ` (${Math.round(c.salary_p25 / 1000)}–${Math.round(c.salary_p75 / 1000)})` : ""}
                          </div>
                          <div className="text-xs text-ink/60">с достижениями ФСП: {c.with_fsp}</div>
                        </Link>
                      ) : <span className="text-sm text-ink/35">пока никого</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
