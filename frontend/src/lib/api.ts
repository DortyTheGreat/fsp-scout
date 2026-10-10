// Тонкий клиент к API: cookie сессии httpOnly ставит бэкенд, фронтенд её не видит и не хранит.
import useSWR, { SWRConfiguration } from "swr";

export const API = "/api/v1";

export class ApiError extends Error {
  status: number;
  code?: string;
  extra?: Record<string, unknown>;
  constructor(status: number, message: string, code?: string, extra?: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.code = code;
    this.extra = extra;
  }
}

function errorMessage(status: number, body: any): ApiError {
  const d = body?.detail;
  if (d && typeof d === "object" && !Array.isArray(d) && d.message) return new ApiError(status, d.message, d.code, d);
  if (Array.isArray(d)) {
    const first = d[0];
    const field = Array.isArray(first?.loc) ? first.loc[first.loc.length - 1] : "";
    const msg = String(first?.msg || "Проверьте введённые данные").replace(/^Value error, /, "");
    return new ApiError(status, field && field !== "body" ? `${msg} (${field})` : msg, "validation");
  }
  if (typeof d === "string") return new ApiError(status, d);
  return new ApiError(status, status >= 500 ? "Сервер временно недоступен, попробуйте ещё раз" : "Запрос не выполнен");
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; form?: FormData } = {}): Promise<T> {
  const init: RequestInit = { method: opts.method || (opts.body || opts.form ? "POST" : "GET"), credentials: "include" };
  if (opts.form) init.body = opts.form;
  else if (opts.body !== undefined) {
    init.body = JSON.stringify(opts.body);
    init.headers = { "Content-Type": "application/json" };
  }
  const res = await fetch(`${API}${path}`, init);
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) throw errorMessage(res.status, data);
  return data as T;
}

export function useApi<T = any>(path: string | null, cfg?: SWRConfiguration) {
  return useSWR<T>(path, (p: string) => api<T>(p), { revalidateOnFocus: false, ...cfg });
}

export function qs(params: Record<string, unknown>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    if (Array.isArray(v)) v.forEach((x) => u.append(k, String(x)));
    else u.append(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

/** Склонение: plural(5, ["результат", "результата", "результатов"]) → «результатов». */
export function plural(n: number, forms: [string, string, string]): string {
  const a = Math.abs(n) % 100, b = a % 10;
  if (a > 10 && a < 20) return forms[2];
  if (b > 1 && b < 5) return forms[1];
  if (b === 1) return forms[0];
  return forms[2];
}
const RES: [string, string, string] = ["результат", "результата", "результатов"];
export const results = (n: number) => `${n} ${plural(n, RES)}`;

export const rub = (x?: number | null) => (x ? `${Math.round(x / 1000).toLocaleString("ru-RU")} тыс. ₽` : "—");
export const rubRange = (a?: number | null, b?: number | null) =>
  a && b ? `${Math.round(a / 1000)}–${Math.round(b / 1000)} тыс. ₽` : a ? `от ${rub(a)}` : b ? `до ${rub(b)}` : "не указано";

export const dateRu = (s?: string | null) =>
  s ? new Date(s).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" }) : "—";

export const daysAgo = (s?: string | null) => {
  if (!s) return "давно";
  const d = Math.floor((Date.now() - new Date(s).getTime()) / 86400000);
  if (d <= 0) return "сегодня";
  if (d === 1) return "вчера";
  if (d < 5) return `${d} дня назад`;
  if (d < 21) return `${d} дней назад`;
  if (d < 60) return `${Math.round(d / 7)} нед. назад`;
  return `${Math.round(d / 30)} мес. назад`;
};
