"use client";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { FspBlock } from "@/components/domain";
import { Button, ErrorNote, Loading, Modal, PageHead, Panel, Toggle, useToast } from "@/components/ui";
import { api, dateRu, useApi } from "@/lib/api";
import { useSession } from "@/lib/session";

const PRIVACY: [string, string, string][] = [
  ["show_full_name", "Показывать фамилию", "Иначе до принятия приглашения работодатель видит «Иван И.»"],
  ["show_city", "Показывать город", ""],
  ["show_experience", "Показывать опыт работы и стаж", ""],
  ["show_about", "Показывать раздел «О себе»", ""],
  ["show_salary", "Показывать зарплатные ожидания", "Помогает компаниям не присылать заведомо неподходящие предложения"],
  ["show_fsp", "Показывать достижения ФСП", ""],
];

function Settings() {
  const sp = useSearchParams();
  const { data: p, mutate } = useApi<any>("/candidate/profile");
  const { data: consents, mutate: mc } = useApi<any>("/auth/consents");
  const { logout } = useSession();
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [del, setDel] = useState(false);
  const toast = useToast();
  if (!p || !consents) return <Loading />;
  const fspState = sp.get("fsp");

  async function privacy(k: string, v: boolean) {
    await api("/candidate/privacy", { method: "PUT", body: { [k]: v } });
    mutate();
  }
  async function consent(kind: string, granted: boolean) {
    await mc(await api("/auth/consents", { body: { kind, granted } }), { revalidate: false });
    mutate();
    toast.show(granted ? "Согласие сохранено" : "Согласие отозвано");
  }
  async function fsp(action: "refresh" | "unlink") {
    setBusy(true);
    setErr(null);
    try { await api(action === "refresh" ? "/fsp/refresh" : "/fsp/link", { method: action === "refresh" ? "POST" : "DELETE" }); mutate(); }
    catch (e) { setErr(e); } finally { setBusy(false); }
  }

  return (
    <>
      <PageHead title="Приватность и ФСП" />
      {toast.node}
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Аккаунт ФСП" className="lg:col-span-2">
          {fspState === "linked" && <p className="mb-4 rounded-lg bg-emerald-50 px-4 py-3 text-sm font-semibold text-ok">ФСП ID привязан, достижения загружены и проверены по подписи ФСП.</p>}
          {fspState === "error" && <p className="mb-4 rounded-lg bg-signal-50 px-4 py-3 text-sm text-signal-600">Не удалось привязать ФСП ID: {sp.get("reason")}</p>}
          <p className="mb-4 text-[15px] text-ink/70">
            Достижения в соревнованиях ФСП — независимое подтверждение навыков: они поднимают вас внутри категории.
            Если истории в ФСП нет, ничего страшного — категорию определяет тест.
          </p>
          {p.fsp.linked ? (
            <>
              <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
                <span>ФСП ID: <b>{p.fsp.fsp_id}</b></span>
                {p.fsp.fetched_at && <span className="text-ink/55">обновлено {dateRu(p.fsp.fetched_at)}</span>}
                <Button size="sm" variant="secondary" onClick={() => fsp("refresh")} loading={busy}>Обновить</Button>
                <Button size="sm" variant="ghost" onClick={() => fsp("unlink")}>Отвязать</Button>
              </div>
              <FspBlock fsp={p.fsp} />
            </>
          ) : (
            <Button href="/api/v1/fsp/link/start" variant="plum">Войти через ФСП ID</Button>
          )}
          <ErrorNote error={err} />
        </Panel>

        <Panel title="Что видит работодатель">
          <Toggle checked={p.open_to_offers} onChange={async (v) => { await api("/candidate/profile", { method: "PUT", body: { open_to_offers: v } }); mutate(); }}
                  label="Открыт к предложениям" hint="Если выключить, профиль пропадёт из подборок, но останется у вас" />
          {PRIVACY.map(([k, label, hint]) => (
            <Toggle key={k} checked={!!p.privacy?.[k]} onChange={(v) => privacy(k, v)} label={label} hint={hint || undefined} />
          ))}
          <p className="mt-3 text-xs text-ink/55">Контакты (телефон, email, Telegram) не видны никогда — до тех пор, пока вы сами не примете приглашение или не откликнетесь.</p>
        </Panel>

        <Panel title="Согласия на обработку данных">
          {(["processing", "publication", "fsp_data"] as const).map((k) => (
            <div key={k} className="border-b border-mist py-2 last:border-0">
              <Toggle checked={!!consents.current[k]} onChange={(v) => consent(k, v)} label={
                { processing: "Обработка персональных данных", publication: "Показ профиля работодателям", fsp_data: "Получение данных из реестра ФСП" }[k]}
                      hint={consents.texts[k]} />
            </div>
          ))}
          <p className="mt-3 text-xs text-ink/55">Каждое изменение сохраняется с датой и версией текста согласия (152-ФЗ).</p>
          <Button variant="danger" size="sm" className="mt-5" onClick={() => setDel(true)}>Удалить аккаунт и все данные</Button>
        </Panel>
      </div>
      <Modal open={del} onClose={() => setDel(false)} title="Удалить аккаунт?">
        <p className="text-[15px] text-ink/70">Профиль, результаты тестов, приглашения и отклики будут удалены безвозвратно.</p>
        <div className="mt-5 flex justify-end gap-3">
          <Button variant="ghost" onClick={() => setDel(false)}>Отмена</Button>
          <Button variant="danger" onClick={async () => { await api("/auth/me", { method: "DELETE" }); await logout(); }}>Удалить</Button>
        </div>
      </Modal>
    </>
  );
}

export default function Page() {
  return <Suspense><Settings /></Suspense>;
}
