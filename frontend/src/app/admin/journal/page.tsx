"use client";
import { useState } from "react";
import { Loading, PageHead, Tabs } from "@/components/ui";
import { useApi } from "@/lib/api";

const ACTIONS: Record<string, string> = {
  contacts_revealed: "Раскрыты контакты", grade_change: "Смена грейда", fsp_linked: "Привязан ФСП ID", consent: "Изменено согласие",
  view_candidate: "Просмотр карточки", account_deleted: "Удалён аккаунт", aberrant_result: "Неправдоподобный паттерн ответов",
};

export default function Journal() {
  const [tab, setTab] = useState<"audit" | "outbox" | "users">("audit");
  const { data: audit } = useApi<any[]>(tab === "audit" ? "/admin/audit?limit=200" : null);
  const { data: outbox } = useApi<any[]>(tab === "outbox" ? "/admin/outbox" : null);
  const { data: users } = useApi<any[]>(tab === "users" ? "/admin/users" : null);
  const t = (s: string) => new Date(s).toLocaleString("ru-RU");
  return (
    <>
      <PageHead title="Журнал и письма" sub="Значимые действия с персональными данными фиксируются в журнале (152-ФЗ)." />
      <div className="mb-5 max-w-md"><Tabs value={tab} onChange={setTab} items={[{ value: "audit", label: "Журнал действий" }, { value: "outbox", label: "Письма" }, { value: "users", label: "Пользователи" }]} /></div>
      <div className="panel overflow-x-auto">
        {tab === "audit" && (!audit ? <Loading /> : (
          <table className="w-full min-w-[640px] text-left text-sm"><tbody>
            {audit.map((a) => <tr key={a.id} className="border-b border-mist"><td className="px-4 py-2 text-ink/55">{t(a.at)}</td><td className="px-4 py-2">{ACTIONS[a.action] || a.action}</td>
              <td className="px-4 py-2 text-ink/55">польз. {a.actor ?? "—"} → {a.target_type} {a.target_id ?? ""}</td><td className="px-4 py-2 text-xs text-ink/50">{JSON.stringify(a.meta)}</td></tr>)}
          </tbody></table>
        ))}
        {tab === "outbox" && (!outbox ? <Loading /> : (
          <table className="w-full min-w-[640px] text-left text-sm"><tbody>
            {outbox.map((m) => <tr key={m.id} className="border-b border-mist"><td className="px-4 py-2 text-ink/55">{t(m.at)}</td><td className="px-4 py-2">{m.to}</td><td className="px-4 py-2">{m.subject}</td></tr>)}
          </tbody></table>
        ))}
        {tab === "users" && (!users ? <Loading /> : (
          <table className="w-full min-w-[640px] text-left text-sm"><tbody>
            {users.map((u) => <tr key={u.id} className="border-b border-mist"><td className="px-4 py-2">{u.id}</td><td className="px-4 py-2">{u.email}</td><td className="px-4 py-2">{u.role}</td>
              <td className="px-4 py-2">{u.verified ? "подтверждён" : "не подтверждён"}</td><td className="px-4 py-2 text-ink/55">{t(u.created_at)}</td></tr>)}
          </tbody></table>
        ))}
      </div>
    </>
  );
}
