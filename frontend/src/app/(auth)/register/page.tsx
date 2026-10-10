"use client";
import clsx from "clsx";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Button, ErrorNote, Field } from "@/components/ui";
import { api } from "@/lib/api";

function RegisterForm() {
  const sp = useSearchParams();
  const router = useRouter();
  const [role, setRole] = useState<"candidate" | "employer">((sp.get("role") as "employer") === "employer" ? "employer" : "candidate");
  const [f, setF] = useState({ email: "", password: "", name: "", processing: false, publication: true });
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await api("/auth/register", {
        body: {
          email: f.email, password: f.password, role, consent_processing: f.processing,
          consent_publication: role === "candidate" ? f.publication : false,
          full_name: role === "candidate" ? f.name : undefined, company_name: role === "employer" ? f.name : undefined,
        },
      });
      router.push(`/check-email?email=${encodeURIComponent(f.email)}`);
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel p-6 sm:p-8">
      <h1 className="text-2xl font-extrabold">Регистрация</h1>
      <div className="mt-5 grid grid-cols-2 gap-2" role="radiogroup" aria-label="Кто вы">
        {([["candidate", "Ищу работу"], ["employer", "Ищу специалистов"]] as const).map(([v, l]) => (
          <button key={v} type="button" role="radio" aria-checked={role === v} onClick={() => setRole(v)}
                  className={clsx("rounded-xl border-2 px-3 py-3 text-sm font-bold transition-colors",
                    role === v ? "border-plum bg-plum text-white" : "border-mist-300 bg-white text-plum hover:border-plum/50")}>
            {l}
          </button>
        ))}
      </div>
      <form className="mt-5 space-y-4" onSubmit={submit}>
        <Field label={role === "candidate" ? "Фамилия и имя" : "Название компании"}>
          <input className="input" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })}
                 autoComplete={role === "candidate" ? "name" : "organization"} />
        </Field>
        <Field label="Электронная почта" hint="Пришлём ссылку для подтверждения">
          <input className="input" type="email" required autoComplete="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        </Field>
        <Field label="Пароль" hint="Не короче 8 символов">
          <input className="input" type="password" required minLength={8} autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        </Field>
        <label className="flex gap-3 text-sm">
          <input type="checkbox" className="mt-1 h-4 w-4 accent-plum" checked={f.processing} onChange={(e) => setF({ ...f, processing: e.target.checked })} required />
          <span>Согласен на обработку персональных данных в целях подбора работы (152-ФЗ)</span>
        </label>
        {role === "candidate" && (
          <label className="flex gap-3 text-sm">
            <input type="checkbox" className="mt-1 h-4 w-4 accent-plum" checked={f.publication} onChange={(e) => setF({ ...f, publication: e.target.checked })} />
            <span>Показывать работодателям мой профиль без контактов: категорию, оценки навыков и достижения. Можно изменить в любой момент.</span>
          </label>
        )}
        <ErrorNote error={err} />
        <Button type="submit" loading={busy} className="w-full">Создать аккаунт</Button>
      </form>
      <p className="mt-5 text-sm text-ink/65">Уже зарегистрированы? <Link href="/login" className="link">Войдите</Link></p>
    </div>
  );
}

export default function RegisterPage() {
  return <Suspense><RegisterForm /></Suspense>;
}
