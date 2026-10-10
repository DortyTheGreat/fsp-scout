"use client";
import clsx from "clsx";
import Link from "next/link";
import { LevelScale, SkillList } from "@/components/domain";
import { Button, Chip, Loading, PageHead, Panel } from "@/components/ui";
import { daysAgo, rubRange, useApi } from "@/lib/api";
import { useDict } from "@/lib/session";
import type { Invitation } from "@/lib/types";

export default function CandidateHome() {
  const { data: st } = useApi<any>("/candidate/status");
  const { data: prof } = useApi<any>("/candidate/profile");
  const { data: inv } = useApi<Invitation[]>("/invitations");
  const { data: ins } = useApi<any>("/candidate/insights");
  const { gradeName } = useDict();
  if (!st || !prof) return <Loading />;
  const cat = st.category;
  const fresh = (inv || []).filter((i) => i.status === "sent" || i.status === "viewed");
  const next = st.steps.find((s: any) => !s.done && !s.optional);
  const nextHref: Record<string, string> = {
    survey: "/candidate/onboarding", test: "/candidate/test", profile: "/candidate/profile", publication: "/candidate/settings",
  };

  return (
    <>
      <PageHead title={prof.full_name ? `Здравствуйте, ${prof.full_name.split(" ")[1] || prof.full_name}` : "Мой статус"}
                sub={st.visible_to_employers ? "Профиль виден работодателям. Приглашения появятся в разделе «Приглашения»."
                  : "Пока профиль не виден работодателям — осталось несколько шагов."} />

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Panel>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm text-ink/55">Категория, которую видит работодатель</div>
              <div className="mt-1 text-[26px] font-extrabold leading-tight text-plum">
                {cat.grade ? `${cat.specialization_name}, ${cat.grade_name}` : cat.specialization_name ? `${cat.specialization_name}, грейд не подтверждён` : "Ещё не определена"}
              </div>
            </div>
            {st.grade_assigned_at && <Chip tone="ok">подтверждена {daysAgo(st.grade_assigned_at)}</Chip>}
          </div>
          {st.theta !== null ? (
            <LevelScale theta={st.theta} se={st.theta_se} current={cat.grade} />
          ) : (
            <p className="mt-4 text-[15px] text-ink/65">
              Категорию определяет тест на выбранный вами грейд — не резюме. Обычно это 15–25 заданий и около 25 минут.
            </p>
          )}
          <div className="mt-6 flex flex-wrap gap-3">
            {next ? <Button href={nextHref[next.key]}>{
              { survey: "Пройти опрос", test: "Пройти тест", profile: "Заполнить профиль", publication: "Открыть профиль работодателям" }[next.key as string]
            }</Button> : <Button href="/candidate/test" variant="secondary">Тесты и смена грейда</Button>}
            {st.active_attempt_id && <Button href={`/candidate/test/${st.active_attempt_id}`} variant="plum">Продолжить тест</Button>}
          </div>
        </Panel>

        <Panel title="Шаги">
          <ol className="space-y-3">
            {st.steps.map((s: any, i: number) => (
              <li key={s.key} className="flex items-center gap-3">
                <span className={clsx("flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold",
                  s.done ? "bg-ok text-white" : "bg-mist text-plum")}>{s.done ? "✓" : i + 1}</span>
                <Link href={nextHref[s.key] || "/candidate/settings"} className={clsx("text-[15px]", s.done ? "text-ink/55" : "font-semibold text-plum hover:underline")}>
                  {s.title}
                </Link>
              </li>
            ))}
          </ol>
        </Panel>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Panel title="Новые приглашения" action={<Link href="/candidate/invitations" className="link text-sm">Все приглашения</Link>}>
          {fresh.length === 0 ? (
            <p className="text-sm text-ink/60">Пока нет. Работодатели находят кандидатов по категории — чем свежее и полнее профиль, тем выше вы в выдаче.</p>
          ) : (
            <ul className="divide-y divide-mist">
              {fresh.slice(0, 4).map((i) => (
                <li key={i.id} className="py-3">
                  <Link href={`/candidate/invitations?open=${i.id}`} className="block">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-semibold text-plum">{i.title}</span>
                      {i.status === "sent" && <Chip tone="signal">новое</Chip>}
                    </div>
                    <div className="text-sm text-ink/60">{i.company.name}, {rubRange(i.salary_from, i.salary_to)}</div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Что ищут работодатели в вашей категории">
          {!ins?.top_skills?.length ? <p className="text-sm text-ink/60">{cat.grade ? "Активных запросов работодателей по вашей специализации пока нет." : "Появится, когда у вас будет категория."}</p> : (
            <>
              <div className="flex flex-wrap gap-1.5">
                {ins.top_skills.map((s: any) => <Chip key={s.slug} tone="plum">{s.name}</Chip>)}
              </div>
              {(ins.unconfirmed?.length > 0 || ins.weak?.length > 0) && (
                <p className="mt-4 text-sm text-ink/70">
                  {ins.unconfirmed?.length > 0 && <>Не подтверждено тестом: <b>{ins.unconfirmed.join(", ")}</b>. </>}
                  {ins.weak?.length > 0 && <>Оценка ниже 50: <b>{ins.weak.join(", ")}</b>. </>}
                  Короткие задания от компаний и повторный тест обновят профиль.
                </p>
              )}
              {ins.next_grade && <p className="mt-3 text-sm text-ink/60">Следующий грейд — {gradeName(ins.next_grade)}. Смена грейда возможна не чаще раза в 90 дней.</p>}
            </>
          )}
        </Panel>
      </div>

      {prof.skills?.length > 0 && (
        <Panel title="Подтверждённые навыки" className="mt-6" action={<Link href="/candidate/profile" className="link text-sm">Профиль и PDF</Link>}>
          <SkillList skills={prof.skills} limit={8} />
        </Panel>
      )}
    </>
  );
}
