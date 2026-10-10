"use client";
import Link from "next/link";
import { useState } from "react";
import { Button, Empty, Loading, PageHead, StatusChip, Tabs } from "@/components/ui";
import { api, dateRu, rubRange, useApi } from "@/lib/api";
import { useDict } from "@/lib/session";
import type { Invitation } from "@/lib/types";

export default function EmpInvitations() {
  const { data, mutate } = useApi<Invitation[]>("/invitations");
  const { reasonName } = useDict();
  const [tab, setTab] = useState<string>("all");
  if (!data) return <Loading />;
  const list = tab === "all" ? data : data.filter((i) => i.status === tab);
  const count = (s: string) => data.filter((i) => i.status === s).length;
  return (
    <>
      <PageHead title="Приглашения" sub="Статусы обновляются, когда кандидат открывает приглашение и отвечает. Контакты появляются после принятия." />
      <div className="mb-5">
        <Tabs value={tab} onChange={setTab} items={[{ value: "all", label: `Все (${data.length})` }, { value: "sent", label: `Не открыты (${count("sent")})` },
          { value: "viewed", label: `Просмотрены (${count("viewed")})` }, { value: "accepted", label: `Приняты (${count("accepted")})` }, { value: "declined", label: `Отклонены (${count("declined")})` }]} />
      </div>
      {list.length === 0 ? <Empty title="Здесь пока пусто" action={<Button href="/employer/needs">К подборкам</Button>} /> : (
        <div className="panel divide-y divide-mist">
          {list.map((i) => (
            <div key={i.id} className="flex flex-wrap items-center gap-4 px-5 py-4">
              <div className="min-w-0 flex-1">
                <Link href={`/employer/candidates/${i.candidate?.id}`} className="font-bold text-plum hover:underline">{i.candidate?.name}</Link>
                <div className="text-sm text-ink/60">{i.title}; {rubRange(i.salary_from, i.salary_to)}; отправлено {dateRu(i.created_at)}</div>
                {i.status === "declined" && <div className="mt-1 text-sm">Причина: <b>{reasonName(i.decline_reason)}</b>{i.decline_comment ? `. «${i.decline_comment}»` : ""}</div>}
                {i.status === "accepted" && i.candidate?.contacts && (
                  <div className="mt-1 text-sm">Контакты: <b>{[i.candidate.contacts.email, i.candidate.contacts.phone, i.candidate.contacts.telegram].filter(Boolean).join(", ")}</b></div>
                )}
              </div>
              {i.match && <span className="text-sm text-ink/55">совпадение {Math.round(i.match.score)}</span>}
              <StatusChip status={i.status} />
              {(i.status === "sent" || i.status === "viewed") && (
                <button className="text-sm font-semibold text-ink/50 underline" onClick={async () => { await api(`/invitations/${i.id}/withdraw`, { method: "POST" }); mutate(); }}>Отозвать</button>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
