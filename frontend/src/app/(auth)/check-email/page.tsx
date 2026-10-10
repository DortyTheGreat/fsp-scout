"use client";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Button } from "@/components/ui";
import { useApi } from "@/lib/api";

function CheckEmail() {
  const email = useSearchParams().get("email") || "";
  const { data } = useApi<{ subject: string; body: string; link: string; at: string }[]>(
    email ? `/demo/mailbox?email=${encodeURIComponent(email)}` : null, { shouldRetryOnError: false, refreshInterval: 3000 });
  const letter = data?.[0];
  return (
    <div className="panel p-6 sm:p-8">
      <h1 className="text-2xl font-extrabold">Подтвердите почту</h1>
      <p className="mt-3 text-[15px] leading-relaxed text-ink/70">
        Мы отправили письмо на <b>{email}</b>. Перейдите по ссылке из письма — после этого откроется личный кабинет.
      </p>
      {letter && (
        <div className="mt-6 rounded-xl border border-dashed border-plum/30 bg-plum-50 p-4">
          <div className="text-sm font-bold text-plum">Демо-режим: письмо доступно здесь</div>
          <p className="mt-1 text-sm text-ink/65">В боевом режиме письма уходят через SMTP, этот блок выключен.</p>
          <div className="mt-3 rounded-lg bg-white p-3 text-sm">
            <div className="font-semibold">{letter.subject}</div>
            <p className="mt-1 text-ink/70">{letter.body}</p>
          </div>
          <Button href={new URL(letter.link).pathname + new URL(letter.link).search} className="mt-3 w-full">Подтвердить адрес</Button>
        </div>
      )}
    </div>
  );
}

export default function Page() {
  return <Suspense><CheckEmail /></Suspense>;
}
