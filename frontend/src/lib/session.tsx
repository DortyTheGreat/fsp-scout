"use client";
import { createContext, useContext } from "react";
import { useApi, api } from "./api";
import type { Dict, User } from "./types";

interface Session {
  user: User | null | undefined;
  loading: boolean;
  refresh: () => Promise<unknown>;
  logout: () => Promise<void>;
  dict: Dict | undefined;
}

const Ctx = createContext<Session>({ user: undefined, loading: true, refresh: async () => {}, logout: async () => {}, dict: undefined });

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const { data, error, isLoading, mutate } = useApi<User>("/auth/me", { shouldRetryOnError: false });
  const { data: dict } = useApi<Dict>("/dictionaries", { revalidateIfStale: false });
  const user = error ? null : data;
  return (
    <Ctx.Provider
      value={{
        user,
        loading: isLoading,
        refresh: () => mutate(),
        logout: async () => {
          await api("/auth/logout", { method: "POST" });
          await mutate(undefined, { revalidate: false });
          window.location.href = "/";
        },
        dict,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export const useSession = () => useContext(Ctx);

export function useDict() {
  const { dict } = useSession();
  const skillName = (s: string) => dict?.skills.find((x) => x.slug === s)?.name || s;
  const specName = (s?: string | null) => dict?.specializations.find((x) => x.slug === s)?.name || s || "—";
  const gradeName = (s?: string | null) => dict?.grades.find((x) => x.slug === s)?.name || s || "—";
  const formatName = (s?: string | null) => dict?.work_formats.find((x) => x.slug === s)?.name || s || "—";
  const reasonName = (s?: string | null) => dict?.decline_reasons.find((x) => x.slug === s)?.name || s || "—";
  return { dict, skillName, specName, gradeName, formatName, reasonName };
}
