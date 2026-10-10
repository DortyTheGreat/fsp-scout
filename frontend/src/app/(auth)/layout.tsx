import { Logo } from "@/components/shell";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-mist-50">
      <header className="mx-auto max-w-5xl px-4 py-5 sm:px-8"><Logo /></header>
      <main className="mx-auto max-w-md px-4 pb-16 pt-4">{children}</main>
    </div>
  );
}
