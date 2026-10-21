"use client";
import clsx from "clsx";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { InvitationThread } from "@/components/thread";
import { Button, Chip, Empty, ErrorNote, Field, Loading, Modal, PageHead, Panel, StatusChip, Tabs } from "@/components/ui";
import { api, dateRu, rub, rubRange, useApi } from "@/lib/api";
import { useDict } from "@/lib/session";
import type { Invitation } from "@/lib/types";

function Detail({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const { data: inv, mutate } = useApi<Invitation>(`/invitations/${id}`);
  const { dict, formatName, reasonName } = useDict();
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (inv) onChanged(); }, [inv?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  async function act(path: string, body?: unknown) {
    setBusy(true);
    setErr(null);
    try { await mutate(await api(`/invitations/${id}/${path}`, { method: "POST", body }), { revalidate: true }); setDeclining(false); }
    catch (e) { setErr(e); } finally { setBusy(false); }
  }

  return (
    <Modal open onClose={onClose} title={inv?.title || "Приглашение"} wide>
      {!inv ? <Loading /> : (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-3">
            <StatusChip status={inv.status} />
            <span className="text-sm text-ink/55">получено {dateRu(inv.created_at)}</span>
          </div>
          <div className="grid gap-4 rounded-xl bg-plum-50 p-4 sm:grid-cols-2 lg:grid-cols-4">
            <div><div className="text-xs text-ink/55">Компания</div><div className="font-bold text-plum">{inv.company.name}</div></div>
            <div><div className="text-xs text-ink/55">Зарплата</div><div className="font-bold text-plum">{rubRange(inv.salary_from, inv.salary_to)}</div></div>
            <div><div className="text-xs text-ink/55">Формат</div><div className="font-bold text-plum">{inv.work_format ? formatName(inv.work_format) : "обсуждается"}</div></div>
            <div className="min-w-0"><div className="text-xs text-ink/55">Способ связи</div><div className="break-words text-sm font-bold text-plum [overflow-wrap:anywhere]">{inv.contact_method}</div></div>
          </div>
          {inv.salary_context && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Chip tone={inv.salary_context.verdict === "below" ? "warn" : inv.salary_context.verdict === "unknown" ? "mist" : "ok"}>
                {({ below: "ниже ожиданий", covers: "не ниже ожиданий", overlaps: "в пределах ожиданий", unknown: "ожидания не указаны" } as const)[inv.salary_context.verdict]}
              </Chip>
              <span className="text-ink/70">{inv.salary_context.text}
                {inv.salary_context.candidate_from ? ` (ваши ожидания — ${rubRange(inv.salary_context.candidate_from, inv.salary_context.candidate_to)})` : ""}.
                {inv.salary_context.category_median ? ` Медиана ожиданий в вашей категории — ${rub(inv.salary_context.category_median)}.` : ""}</span>
            </div>
          )}
          <div>
            <div className="mb-1 font-semibold">Предложение</div>
            <p className="whitespace-pre-line text-[15px] leading-relaxed text-ink/80">{inv.description}</p>
          </div>
          {inv.company.description && <p className="text-sm text-ink/60">О компании: {inv.company.description}</p>}
          {inv.match_summary && <p className="text-sm text-ink/60">Почему вас пригласили: {inv.match_summary}</p>}
          {inv.status === "accepted" && (
            <div className="rounded-xl border border-ok/30 bg-emerald-50 p-4">
              <div className="font-semibold text-ok">Вы приняли приглашение</div>
              <p className="mt-1 text-sm">Компания видит ваши контакты и свяжется с вами. Написать ей: <b>{inv.contact_method}</b></p>
            </div>
          )}
          {inv.status === "declined" && <p className="text-sm text-ink/60">Вы отклонили приглашение: {reasonName(inv.decline_reason)}.</p>}
          <InvitationThread invId={inv.id} role="candidate" messages={inv.messages || []} companyName={inv.company.name}
                            closed={inv.status === "declined" || inv.status === "withdrawn"}
                            onChange={(m) => mutate({ ...inv, messages: m, status: inv.status === "sent" ? "viewed" : inv.status }, { revalidate: false })} />
          <ErrorNote error={err} />
          {(inv.status === "sent" || inv.status === "viewed") && !declining && (
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => act("accept")} loading={busy}>Принять и открыть контакты</Button>
              <Button variant="secondary" onClick={() => setDeclining(true)}>Отклонить</Button>
            </div>
          )}
          {declining && (
            <div className="space-y-3 rounded-xl border border-mist-300 p-4">
              <p className="text-sm text-ink/65">Причина поможет компании скорректировать предложение, а системе — точнее подбирать приглашения.</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {dict?.decline_reasons.map((r) => (
                  <label key={r.slug} className={clsx("flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm",
                    reason === r.slug ? "border-plum bg-plum-50" : "border-mist-300")}>
                    <input type="radio" name="reason" className="accent-plum" checked={reason === r.slug} onChange={() => setReason(r.slug)} />{r.name}
                  </label>
                ))}
              </div>
              <Field label="Комментарий (необязательно)"><textarea className="input" value={comment} onChange={(e) => setComment(e.target.value)} /></Field>
              <div className="flex gap-3">
                <Button variant="danger" disabled={!reason} loading={busy} onClick={() => act("decline", { reason, comment: comment || null })}>Отклонить приглашение</Button>
                <Button variant="ghost" onClick={() => setDeclining(false)}>Отмена</Button>
              </div>
            </div>
          )}
          {inv.history && (
            <div className="text-xs text-ink/50">
              История: {inv.history.map((h) => `${dateRu(h.at)} — ${({ sent: "отправлено", viewed: "просмотрено", accepted: "принято", declined: "отклонено", withdrawn: "отозвано" } as any)[h.status] || h.status}`).join("; ")}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

function Invitations() {
  const sp = useSearchParams();
  const { data, mutate } = useApi<Invitation[]>("/invitations");
  const [tab, setTab] = useState<"new" | "all">("new");
  const [open, setOpen] = useState<number | null>(sp.get("open") ? Number(sp.get("open")) : null);
  if (!data) return <Loading />;
  const list = tab === "new" ? data.filter((i) => i.status === "sent" || i.status === "viewed") : data;
  return (
    <>
      <PageHead title="Приглашения" sub="Компании пишут первыми и сразу указывают зарплату и способ связи. Вопросы можно задать до ответа — ваши контакты откроются только той компании, чьё приглашение вы примете." />
      <div className="mb-5 max-w-sm"><Tabs value={tab} onChange={setTab} items={[{ value: "new", label: "Ждут ответа" }, { value: "all", label: "Все" }]} /></div>
      {list.length === 0 ? (
        <Empty title={tab === "new" ? "Новых приглашений нет" : "Приглашений пока нет"}
               text="Работодатели находят кандидатов по категории. Подтвердите навыки тестом и решайте короткие задания — так вы будете выше в выдаче." />
      ) : (
        <div className="space-y-3">
          {list.map((i) => (
            <button key={i.id} onClick={() => setOpen(i.id)} className="panel block w-full p-5 text-left hover:border-plum/40">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-lg font-bold text-plum">{i.title}</div>
                  <div className="mt-0.5 text-[15px] text-ink/70">{i.company.name}</div>
                </div>
                <div className="text-right">
                  <div className="font-extrabold text-plum">{rubRange(i.salary_from, i.salary_to)}</div>
                  {i.salary_context && i.salary_context.verdict !== "unknown" && (
                    <div className="text-xs text-ink/55">{({ below: "ниже ваших ожиданий", covers: "не ниже ваших ожиданий", overlaps: "в пределах ожиданий" } as const)[i.salary_context.verdict]}</div>
                  )}
                  <div className="mt-1 flex items-center justify-end gap-2">
                    {!!i.messages_count && <Chip tone="lavender">вопросы: {i.messages_count}</Chip>}
                    <StatusChip status={i.status} />
                  </div>
                </div>
              </div>
              <p className="mt-2 line-clamp-2 text-sm text-ink/60">{i.description}</p>
            </button>
          ))}
        </div>
      )}
      {open && <Detail id={open} onClose={() => setOpen(null)} onChanged={() => mutate()} />}
      <Panel className="mt-8" title="Как это работает">
        <p className="text-sm text-ink/65">Вилку, название компании и способ связи вы видите сразу — до начала общения. До ответа можно задать компании вопрос: она увидит его без ваших контактов. Статусы видят обе стороны: «отправлено» → «просмотрено» (когда вы открыли приглашение) → «принято» или «отклонено». После принятия компания получает ваши контакты.</p>
      </Panel>
    </>
  );
}

export default function Page() {
  return <Suspense><Invitations /></Suspense>;
}
