"use client";
import clsx from "clsx";
import { useState } from "react";
import { Button, ErrorNote } from "@/components/ui";
import { api, dateRu } from "@/lib/api";
import type { InvitationMessage } from "@/lib/types";

const QUICK = ["Можно ли работать полностью удалённо?", "Какой стек и состав команды?", "Возможен ли пересмотр вилки?",
  "Какие этапы отбора?"];

/** Вопросы и ответы по приглашению до раскрытия контактов. Кандидат — «вы», компания — по названию. */
export function InvitationThread({ invId, role, messages, closed, companyName, onChange }: {
  invId: number; role: "candidate" | "employer"; messages: InvitationMessage[]; closed: boolean; companyName: string;
  onChange: (m: InvitationMessage[]) => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);

  async function send(t: string) {
    if (t.trim().length < 2) return;
    setBusy(true);
    setErr(null);
    try {
      onChange(await api<InvitationMessage[]>(`/invitations/${invId}/messages`, { method: "POST", body: { text: t } }));
      setText("");
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }

  const who = (r: string) => (r === role ? "Вы" : r === "employer" ? companyName : "Кандидат");
  return (
    <div className="rounded-xl border border-mist-300 p-4">
      <div className="font-semibold">{role === "candidate" ? "Вопросы компании до ответа" : "Вопросы кандидата"}</div>
      <p className="mt-0.5 text-sm text-ink/60">
        {role === "candidate"
          ? "Уточните условия, не раскрывая себя: компания видит вопрос, но ваши контакты — только после того, как вы примете приглашение."
          : "Кандидат уточняет условия до ответа. Его контакты откроются, когда он примет приглашение."}
      </p>
      {messages.length === 0 && role === "employer" && (
        <p className="mt-3 text-sm text-ink/50">Кандидат пока ничего не спрашивал. Можно дополнить приглашение — он увидит сообщение до ответа.</p>
      )}
      {messages.length > 0 && (
        <ul className="mt-3 space-y-2">
          {messages.map((m) => (
            <li key={m.id} className={clsx("max-w-[90%] rounded-lg px-3 py-2 text-[15px]",
              m.author_role === role ? "ml-auto bg-plum-50" : "bg-mist-50")}>
              <div className="text-xs text-ink/55">{who(m.author_role)} · {dateRu(m.created_at)}</div>
              <div className="whitespace-pre-line">{m.text}</div>
            </li>
          ))}
        </ul>
      )}
      {closed ? (
        <p className="mt-3 text-sm text-ink/50">Приглашение закрыто — переписка недоступна.</p>
      ) : (
        <div className="mt-3 space-y-2">
          {role === "candidate" && messages.length === 0 && (
            <div className="flex flex-wrap gap-2">
              {QUICK.map((q) => (
                <button key={q} type="button" onClick={() => setText(q)}
                        className="rounded-full border border-plum/20 px-3 py-1 text-sm text-plum hover:bg-plum-50">{q}</button>
              ))}
            </div>
          )}
          <textarea className="input min-h-20" value={text} maxLength={2000} onChange={(e) => setText(e.target.value)}
                    placeholder={role === "candidate" ? "Ваш вопрос" : messages.length ? "Ваш ответ" : "Сообщение кандидату"} aria-label="Сообщение" />
          <ErrorNote error={err} />
          <Button variant="secondary" size="sm" loading={busy} disabled={text.trim().length < 2} onClick={() => send(text)}>
            {role === "candidate" ? "Задать вопрос" : messages.length ? "Ответить" : "Написать кандидату"}
          </Button>
        </div>
      )}
    </div>
  );
}
