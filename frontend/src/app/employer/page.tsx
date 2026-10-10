"use client";
import Link from "next/link";
import { Button, Empty, Loading, PageHead, Panel, Stat, StatusChip } from "@/components/ui";
import { dateRu, rubRange, useApi } from "@/lib/api";
import { useDict } from "@/lib/session";
import type { Invitation, Need } from "@/lib/types";

export default function EmployerHome() {
  const { data: comp } = useApi<any>("/employer/company");
  const { data: needs } = useApi<Need[]>("/employer/needs");
  const { data: invs } = useApi<Invitation[]>("/invitations");
  const { data: ins } = useApi<any>("/employer/insights");
  const { specName, gradeName } = useDict();
  if (!comp || !needs || !invs || !ins) return <Loading />;
  const active = needs.filter((n) => n.status === "active");
  return (
    <>
      <PageHead title={comp.name || "Ваша компания"} sub="Опишите потребность — система покажет подходящие категории и ранжированных кандидатов с объяснением."
                action={<Button href="/employer/needs?new=1">Новая подборка</Button>} />
      {!comp.name && (
        <Panel className="mb-6 border-signal/40">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p>Заполните название и описание компании — они указываются в каждом приглашении.</p>
            <Button href="/employer/company" variant="plum">Заполнить профиль</Button>
          </div>
        </Panel>
      )}
      <div className="mb-6 grid grid-cols-2 gap-6 rounded-2xl bg-white p-6 sm:grid-cols-4">
        <Stat value={active.length} label="активных подборок" />
        <Stat value={ins.sent} label="приглашений отправлено" />
        <Stat value={ins.accepted} label="приняли приглашение" tone="signal" />
        <Stat value={ins.accept_rate !== null ? `${Math.round(ins.accept_rate * 100)}%` : "—"} label="доля принятых среди ответов" />
      </div>
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Panel title="Подборки" action={<Link href="/employer/needs" className="link text-sm">Все подборки</Link>}>
          {active.length === 0 ? <Empty title="Подборок пока нет" text="Опишите, кто нужен, — и получите список кандидатов." action={<Button href="/employer/needs?new=1">Создать подборку</Button>} /> : (
            <ul className="divide-y divide-mist">
              {active.map((n) => (
                <li key={n.id}>
                  <Link href={`/employer/needs/${n.id}`} className="block py-3 hover:bg-mist-50">
                    <div className="font-semibold text-plum">{n.title}</div>
                    <div className="text-sm text-ink/60">{specName(n.specialization)}, {n.grades.map(gradeName).join(" или ")}, {rubRange(n.salary_from, n.salary_to)}</div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Обратная связь от кандидатов">
          {ins.decline_reasons.length === 0 ? <p className="text-sm text-ink/60">Когда кандидаты начнут отвечать, здесь появятся причины отказов и рекомендации.</p> : (
            <>
              <ul className="space-y-1.5 text-sm">
                {ins.decline_reasons.map((r: any) => (
                  <li key={r.slug} className="flex justify-between gap-3"><span>{r.name}</span><b className="tabular-nums text-plum">{r.count}</b></li>
                ))}
              </ul>
              {ins.tips.length > 0 && (
                <div className="mt-4 space-y-2">
                  {ins.tips.map((t: string, i: number) => <p key={i} className="rounded-lg bg-signal-50 px-3 py-2 text-sm text-ink/80">{t}</p>)}
                </div>
              )}
            </>
          )}
        </Panel>
      </div>
      <Panel title="Последние приглашения" className="mt-6" action={<Link href="/employer/invitations" className="link text-sm">Все приглашения</Link>}>
        {invs.length === 0 ? <p className="text-sm text-ink/60">Вы ещё не отправляли приглашений.</p> : (
          <div className="divide-y divide-mist">
            {invs.slice(0, 6).map((i) => (
              <div key={i.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
                <Link href={`/employer/candidates/${i.candidate?.id}`} className="w-44 truncate font-semibold text-plum hover:underline">{i.candidate?.name}</Link>
                <span className="min-w-0 flex-1 truncate text-ink/70">{i.title}</span>
                <span className="text-ink/50">{dateRu(i.created_at)}</span>
                <StatusChip status={i.status} />
              </div>
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}
