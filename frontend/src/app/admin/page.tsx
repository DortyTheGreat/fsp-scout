"use client";
import { Loading, PageHead, Panel, Stat } from "@/components/ui";
import { useApi } from "@/lib/api";
import { useDict } from "@/lib/session";

export default function AdminHome() {
  const { data: s } = useApi<any>("/admin/stats");
  const { specName, gradeName } = useDict();
  if (!s) return <Loading />;
  const inv = s.invitations || {};
  return (
    <>
      <PageHead title="Сводка платформы" />
      <div className="grid grid-cols-2 gap-6 rounded-2xl bg-white p-6 sm:grid-cols-4">
        <Stat value={s.users.candidate || 0} label="кандидатов" />
        <Stat value={s.candidates_with_category} label="с подтверждённой категорией" />
        <Stat value={s.fsp_linked} label="привязали ФСП ID" tone="signal" />
        <Stat value={s.users.employer || 0} label="работодателей" />
        <Stat value={s.tests_finished} label="тестов завершено" />
        <Stat value={s.avg_items_per_test ?? "—"} label="заданий в среднем на тест" />
        <Stat value={s.tests_passed_share !== null ? `${Math.round(s.tests_passed_share * 100)}%` : "—"} label="тестов пройдено на заявленный грейд" />
        <Stat value={s.invitation_accept_rate !== null ? `${Math.round(s.invitation_accept_rate * 100)}%` : "—"} label="приглашений принято" tone="signal" />
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Panel title="Категории">
          <div className="divide-y divide-mist text-sm">
            {s.categories.map((c: any) => (
              <div key={`${c.specialization}${c.grade}`} className="flex justify-between py-2"><span>{specName(c.specialization)}, {gradeName(c.grade)}</span><b className="tabular-nums text-plum">{c.count}</b></div>
            ))}
          </div>
        </Panel>
        <Panel title="Приглашения и отклики">
          <div className="divide-y divide-mist text-sm">
            {[["sent", "не открыты"], ["viewed", "просмотрены"], ["accepted", "приняты"], ["declined", "отклонены"], ["withdrawn", "отозваны"]].map(([k, l]) => (
              <div key={k} className="flex justify-between py-2"><span>{l}</span><b className="tabular-nums text-plum">{inv[k] || 0}</b></div>
            ))}
            <div className="flex justify-between py-2"><span>вакансий</span><b className="tabular-nums text-plum">{s.vacancies}</b></div>
            <div className="flex justify-between py-2"><span>откликов</span><b className="tabular-nums text-plum">{s.applications}</b></div>
          </div>
        </Panel>
      </div>
    </>
  );
}
