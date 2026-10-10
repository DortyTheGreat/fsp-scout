"use client";
import clsx from "clsx";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useApi } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Role } from "@/lib/types";
import { Loading } from "./ui";

const NAV: Record<Role, { href: string; label: string; badge?: string }[]> = {
  candidate: [
    { href: "/candidate", label: "Мой статус" },
    { href: "/candidate/invitations", label: "Приглашения", badge: "invites" },
    { href: "/candidate/profile", label: "Профиль и резюме" },
    { href: "/candidate/test", label: "Тестирование" },
    { href: "/candidate/tasks", label: "Задания от компаний" },
    { href: "/candidate/vacancies", label: "Вакансии" },
    { href: "/candidate/applications", label: "Мои отклики" },
    { href: "/candidate/settings", label: "Приватность и ФСП" },
  ],
  employer: [
    { href: "/employer", label: "Обзор" },
    { href: "/employer/needs", label: "Подборки" },
    { href: "/employer/categories", label: "Каталог категорий" },
    { href: "/employer/search", label: "Поиск по базе" },
    { href: "/employer/invitations", label: "Приглашения" },
    { href: "/employer/vacancies", label: "Вакансии и отклики" },
    { href: "/employer/tasks", label: "Короткие задания" },
    { href: "/employer/company", label: "Компания" },
  ],
  admin: [
    { href: "/admin", label: "Сводка" },
    { href: "/admin/items", label: "Банк заданий" },
    { href: "/admin/ranking", label: "Модель ранжирования" },
    { href: "/admin/journal", label: "Журнал и письма" },
  ],
};

export function Logo({ light }: { light?: boolean }) {
  return (
    <Link href="/" className={clsx("flex items-center gap-2.5 font-extrabold", light ? "text-white" : "text-plum")}>
      <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden>
        <rect width="30" height="30" rx="8" fill="#FF0053" />
        <path d="M7 20.5 12.5 9h2.2l-5.5 11.5H7Zm6.3 0L18.8 9H21l-5.5 11.5h-2.2Z" fill="#fff" />
        <circle cx="22.5" cy="20" r="2" fill="#fff" />
      </svg>
      <span className="text-[17px] leading-none">ФСП Скаут</span>
    </Link>
  );
}

function NewInvites() {
  const { data } = useApi<any[]>("/invitations?status=sent", { refreshInterval: 30000 });
  if (!data?.length) return null;
  return <span className="ml-auto rounded-full bg-signal px-2 py-0.5 text-[11px] font-bold text-white">{data.length}</span>;
}

export function AppShell({ role, children }: { role: Role; children: React.ReactNode }) {
  const { user, loading, logout } = useSession();
  const router = useRouter();
  const path = usePathname();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [path]);
  useEffect(() => {
    if (loading) return;
    if (user === null) router.replace(`/login?next=${encodeURIComponent(path)}`);
    else if (user && user.role !== role) router.replace(user.role === "admin" ? "/admin" : `/${user.role}`);
  }, [user, loading, role, router, path]);
  if (!user || user.role !== role) return <div className="mx-auto max-w-5xl px-4"><Loading /></div>;
  const items = NAV[role];
  const active = (href: string) => (href === `/${role}` ? path === href : path.startsWith(href));
  const nav = (
    <nav className="flex flex-col gap-0.5" aria-label="Разделы">
      {items.map((it) => (
        <Link
          key={it.href}
          href={it.href}
          className={clsx(
            "flex items-center rounded-lg px-3 py-2.5 text-[15px] font-medium transition-colors",
            active(it.href) ? "bg-white/12 text-white" : "text-white/65 hover:bg-white/5 hover:text-white",
          )}
          aria-current={active(it.href) ? "page" : undefined}
        >
          {active(it.href) && <span className="mr-2.5 h-4 w-1 rounded-full bg-signal" aria-hidden />}
          {it.label}
          {it.badge === "invites" && <NewInvites />}
        </Link>
      ))}
    </nav>
  );
  const roleName = { candidate: "Кандидат", employer: "Работодатель", admin: "Администратор" }[role];
  return (
    <div className="min-h-screen lg:flex">
      <aside className="hidden w-64 shrink-0 flex-col bg-plum px-4 py-6 lg:flex lg:sticky lg:top-0 lg:h-screen">
        <div className="px-2"><Logo light /></div>
        <div className="mt-8 flex-1 overflow-y-auto">{nav}</div>
        <div className="border-t border-white/10 px-2 pt-4 text-sm text-white/70">
          <div className="truncate font-semibold text-white">{user.name || user.email}</div>
          <div className="text-xs">{roleName}</div>
          <button onClick={logout} className="mt-3 text-sm font-semibold text-white/80 underline underline-offset-4 hover:text-white">Выйти</button>
        </div>
      </aside>
      <header className="sticky top-0 z-40 flex items-center justify-between bg-plum px-4 py-3 lg:hidden">
        <Logo light />
        <button onClick={() => setOpen(!open)} className="rounded-lg px-3 py-1.5 text-sm font-semibold text-white ring-1 ring-white/30" aria-expanded={open}>
          {open ? "Закрыть" : "Меню"}
        </button>
      </header>
      {open && (
        <div className="bg-plum px-4 pb-5 lg:hidden">
          {nav}
          <button onClick={logout} className="mt-3 px-3 text-sm font-semibold text-white/80 underline">Выйти</button>
        </div>
      )}
      <main className="min-w-0 flex-1 px-4 py-6 sm:px-8 sm:py-8">
        <div className="mx-auto max-w-6xl">{children}</div>
      </main>
    </div>
  );
}
