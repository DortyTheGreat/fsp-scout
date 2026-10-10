"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { Button, ErrorNote, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { User } from "@/lib/types";

function Verify() {
  const token = useSearchParams().get("token");
  const router = useRouter();
  const { refresh } = useSession();
  const [err, setErr] = useState<unknown>(null);
  const done = useRef(false);
  useEffect(() => {
    if (!token || done.current) return;
    done.current = true;
    api<User>("/auth/verify-email", { body: { token } })
      .then(async (u) => {
        await refresh();
        router.replace(u.role === "candidate" ? "/candidate/onboarding" : u.role === "employer" ? "/employer/company?welcome=1" : "/admin");
      })
      .catch(setErr);
  }, [token, router, refresh]);
  return (
    <div className="panel p-6 sm:p-8">
      <h1 className="text-2xl font-extrabold">Подтверждение почты</h1>
      {err ? (
        <div className="mt-4 space-y-4"><ErrorNote error={err} /><Button href="/login" variant="secondary">Перейти ко входу</Button></div>
      ) : <Loading text="Подтверждаем адрес…" />}
    </div>
  );
}

export default function Page() {
  return <Suspense><Verify /></Suspense>;
}
