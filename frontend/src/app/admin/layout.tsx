import { AppShell } from "@/components/shell";

export default function L({ children }: { children: React.ReactNode }) {
  return <AppShell role="admin">{children}</AppShell>;
}
