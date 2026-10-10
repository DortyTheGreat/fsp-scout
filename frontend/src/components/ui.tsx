"use client";
import clsx from "clsx";
import Link from "next/link";
import { useEffect, useState } from "react";

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "plum";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  href?: string;
};

const btnBase =
  "inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 whitespace-nowrap";
const btnVariants = {
  primary: "bg-signal text-white hover:bg-signal-600",
  plum: "bg-plum text-white hover:bg-plum-700",
  secondary: "border border-plum/25 bg-white text-plum hover:border-plum hover:bg-plum-50",
  ghost: "text-plum hover:bg-plum-50",
  danger: "border border-signal/30 bg-white text-signal-600 hover:bg-signal-50",
};
const btnSizes = { sm: "px-3 py-1.5 text-sm", md: "px-4 py-2.5 text-[15px]", lg: "px-6 py-3.5 text-base" };

export function Button({ variant = "primary", size = "md", loading, href, className, children, ...rest }: BtnProps) {
  const cls = clsx(btnBase, btnVariants[variant], btnSizes[size], className);
  if (href && (href.startsWith("/api") || href.startsWith("http")))
    return (
      <a href={href} className={cls}>
        {children}
      </a>
    );
  if (href)
    return (
      <Link href={href} className={cls}>
        {children}
      </Link>
    );
  return (
    <button className={cls} disabled={loading || rest.disabled} {...rest}>
      {loading && <Spinner small />}
      {children}
    </button>
  );
}

export function Spinner({ small }: { small?: boolean }) {
  return (
    <span
      aria-hidden
      className={clsx("inline-block animate-spin rounded-full border-2 border-current border-r-transparent", small ? "h-4 w-4" : "h-6 w-6")}
    />
  );
}

export function Loading({ text = "Загружаем…" }: { text?: string }) {
  return (
    <div className="flex items-center gap-3 py-10 text-plum/70" role="status">
      <Spinner /> {text}
    </div>
  );
}

export function ErrorNote({ error }: { error?: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="rounded-lg border border-signal/30 bg-signal-50 px-4 py-3 text-sm text-signal-600">
      {msg}
    </div>
  );
}

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={clsx("block", className)}>
      <span className="label">{label}</span>
      {children}
      {hint && <span className="hint block">{hint}</span>}
    </label>
  );
}

export function Panel({ title, action, children, className, pad = true }: {
  title?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode; className?: string; pad?: boolean;
}) {
  return (
    <section className={clsx("panel", pad && "p-5 sm:p-6", className)}>
      {(title || action) && (
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          {title && <h2 className="text-lg font-bold">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Chip({ children, tone = "plum", className }: { children: React.ReactNode; tone?: "plum" | "signal" | "ok" | "mist" | "warn" | "lavender"; className?: string }) {
  const tones = {
    plum: "bg-plum-100 text-plum",
    signal: "bg-signal-100 text-signal-600",
    ok: "bg-emerald-50 text-ok",
    mist: "bg-mist text-ink/70",
    warn: "bg-amber-50 text-warn",
    lavender: "bg-lavender-200/60 text-plum-600",
  };
  return <span className={clsx("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold", tones[tone], className)}>{children}</span>;
}

const STATUS: Record<string, { text: string; tone: "plum" | "signal" | "ok" | "mist" | "warn" | "lavender" }> = {
  sent: { text: "Отправлено", tone: "lavender" },
  viewed: { text: "Просмотрено", tone: "plum" },
  accepted: { text: "Принято", tone: "ok" },
  declined: { text: "Отклонено", tone: "mist" },
  rejected: { text: "Отказ", tone: "mist" },
  withdrawn: { text: "Отозвано", tone: "mist" },
  offered: { text: "Новое", tone: "signal" },
  submitted: { text: "Отправлено", tone: "lavender" },
  reviewed: { text: "Оценено", tone: "ok" },
  skipped: { text: "Пропущено", tone: "mist" },
  passed: { text: "Пройден", tone: "ok" },
  failed: { text: "Не пройден", tone: "warn" },
  needs_confirmation: { text: "Нужно подтверждение", tone: "signal" },
  in_progress: { text: "В процессе", tone: "signal" },
  published: { text: "Опубликована", tone: "ok" },
  draft: { text: "Черновик", tone: "mist" },
  closed: { text: "Закрыта", tone: "mist" },
  active: { text: "Активна", tone: "ok" },
};

export function StatusChip({ status }: { status: string }) {
  const s = STATUS[status] || { text: status, tone: "mist" as const };
  return <Chip tone={s.tone}>{s.text}</Chip>;
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-plum/40 p-0 sm:items-center sm:p-6" onClick={onClose}>
      <div
        role="dialog"
        aria-modal
        aria-label={title}
        className={clsx("max-h-[92vh] w-full overflow-y-auto rounded-t-2xl bg-white p-5 shadow-2xl sm:rounded-2xl sm:p-7", wide ? "sm:max-w-3xl" : "sm:max-w-lg")}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 className="text-xl font-bold">{title}</h2>
          <button onClick={onClose} className="rounded-lg px-2 py-1 text-2xl leading-none text-ink/50 hover:bg-mist-50" aria-label="Закрыть">
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { value: T; label: React.ReactNode }[] }) {
  return (
    <div className="flex gap-1 overflow-x-auto rounded-xl bg-mist p-1" role="tablist">
      {items.map((it) => (
        <button
          key={it.value}
          role="tab"
          aria-selected={value === it.value}
          onClick={() => onChange(it.value)}
          className={clsx(
            "whitespace-nowrap rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors",
            value === it.value ? "bg-white text-plum shadow-sm" : "text-ink/60 hover:text-plum",
          )}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

export function Toggle({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string }) {
  return (
    <label className="flex cursor-pointer items-start gap-3 py-2">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={clsx("relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors", checked ? "bg-plum" : "bg-mist-300")}
      >
        <span className={clsx("absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all", checked ? "left-[22px]" : "left-0.5")} />
      </button>
      <span>
        <span className="block text-[15px] font-medium">{label}</span>
        {hint && <span className="block text-xs text-ink/55">{hint}</span>}
      </span>
    </label>
  );
}

export function Empty({ title, text, action }: { title: string; text?: string; action?: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-plum/20 bg-white/60 px-6 py-12 text-center">
      <p className="text-lg font-bold text-plum">{title}</p>
      {text && <p className="mx-auto mt-2 max-w-md text-sm text-ink/60">{text}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function PageHead({ title, sub, action }: { title: string; sub?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-extrabold sm:text-[28px]">{title}</h1>
        {sub && <p className="mt-1.5 max-w-2xl text-[15px] text-ink/65">{sub}</p>}
      </div>
      {action}
    </div>
  );
}

export function MultiPick({ options, value, onChange, max }: { options: { value: string; label: string }[]; value: string[]; onChange: (v: string[]) => void; max?: number }) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => {
        const on = value.includes(o.value);
        return (
          <button
            type="button"
            key={o.value}
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((x) => x !== o.value) : max && value.length >= max ? value : [...value, o.value])}
            className={clsx(
              "rounded-full border px-3 py-1.5 text-sm font-medium transition-colors",
              on ? "border-plum bg-plum text-white" : "border-mist-300 bg-white text-ink/75 hover:border-plum/50",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function useToast() {
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(() => setMsg(null), 3500);
    return () => clearTimeout(t);
  }, [msg]);
  const node = msg ? (
    <div role="status" className="fixed bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-xl bg-plum px-5 py-3 text-sm font-semibold text-white shadow-xl">
      {msg}
    </div>
  ) : null;
  return { show: setMsg, node };
}

export function Stat({ value, label, tone }: { value: React.ReactNode; label: string; tone?: "signal" }) {
  return (
    <div>
      <div className={clsx("text-3xl font-extrabold tabular-nums", tone === "signal" ? "text-signal" : "text-plum")}>{value}</div>
      <div className="mt-0.5 text-sm text-ink/60">{label}</div>
    </div>
  );
}
