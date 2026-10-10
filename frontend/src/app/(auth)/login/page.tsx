"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Button, ErrorNote, Field } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { User } from "@/lib/types";

function LoginForm() {
  const router = useRouter();
  const sp = useSearchParams();
  const { refresh } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const { data: demo } = useApi<{ role: string; email: string; password: string; note: string }[]>("/demo/accounts", { shouldRetryOnError: false });

  async function login(e?: React.FormEvent, creds?: { email: string; password: string }) {
    e?.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const u = await api<User>("/auth/login", { body: creds || { email, password } });
      await refresh();
      const next = sp.get("next");
      router.push(next && next.startsWith(`/${u.role}`) ? next : u.role === "admin" ? "/admin" : `/${u.role}`);
    } catch (e) {
      setErr(e);
      if (e instanceof ApiError && e.code === "email_not_verified") router.push(`/check-email?email=${encodeURIComponent(email)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="panel p-6 sm:p-8">
        <h1 className="text-2xl font-extrabold">Вход</h1>
        <form className="mt-6 space-y-4" onSubmit={login}>
          <Field label="Электронная почта"><input className="input" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <Field label="Пароль"><input className="input" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
          <ErrorNote error={err} />
          <Button type="submit" loading={busy} className="w-full">Войти</Button>
        </form>
        <p className="mt-5 text-sm text-ink/65">Нет аккаунта? <Link href="/register" className="link">Зарегистрируйтесь</Link></p>
      </div>
      {demo && demo.length > 0 && (
        <div className="mt-6 rounded-2xl border border-plum/15 bg-white/70 p-5">
          <h2 className="font-bold">Демо-доступ для проверки</h2>
          <p className="mt-1 text-sm text-ink/60">Пароль у всех: demo12345</p>
          <div className="mt-3 space-y-2">
            {demo.map((d) => (
              <button key={d.email} onClick={() => login(undefined, d)} className="block w-full rounded-xl border border-mist-300 bg-white px-4 py-3 text-left hover:border-plum">
                <span className="block text-sm font-semibold text-plum">{d.email}</span>
                <span className="block text-xs text-ink/60">{d.note}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

export default function LoginPage() {
  return <Suspense><LoginForm /></Suspense>;
}
