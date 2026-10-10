"use client";
import { useState } from "react";
import { ScoreBar } from "@/components/domain";
import { Button, Chip, Loading, PageHead, Panel } from "@/components/ui";
import { api, dateRu, useApi } from "@/lib/api";

export default function Ranking() {
  const { data, mutate } = useApi<any>("/admin/ranking");
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  if (!data) return <Loading />;
  const active = data.models.find((m: any) => m.active);
  const weights = active?.weights || data.default;
  return (
    <>
      <PageHead title="Модель ранжирования" sub="Итоговая оценка кандидата — взвешенная сумма факторов. Веса стартуют с экспертных и дообучаются на исходах приглашений: кто принял, кто отказал и почему." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title={active ? `Текущие веса (обучены ${dateRu(active.created_at)})` : "Текущие веса (экспертные)"}>
          <div className="space-y-2.5">
            {Object.keys(data.default).map((k) => (
              <div key={k} className="flex items-center gap-3 text-sm">
                <span className="w-48 shrink-0">{data.factor_names[k]}</span>
                <div className="flex-1"><ScoreBar value={weights[k]} max={0.45} /></div>
                <span className="w-24 text-right tabular-nums">{(weights[k] * 100).toFixed(1)}% <span className="text-ink/40">({(data.default[k] * 100).toFixed(0)})</span></span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-ink/55">В скобках — экспертный вес.</p>
          <div className="mt-5 flex flex-wrap gap-3">
            <Button loading={busy} onClick={async () => { setBusy(true); setRes(await api("/admin/ranking/train", { method: "POST" })); setBusy(false); mutate(); }}>Дообучить на исходах приглашений</Button>
            <Button variant="ghost" onClick={async () => { await api("/admin/ranking/reset", { method: "POST" }); setRes(null); mutate(); }}>Вернуть экспертные</Button>
          </div>
        </Panel>
        <Panel title="Как это работает">
          <ul className="space-y-2 text-[15px] text-ink/75">
            <li>Каждое приглашение запоминает факторы кандидата в момент отправки.</li>
            <li>Исход «принято» — положительный пример, «отклонено» — отрицательный. Отказы «сейчас не ищу работу» не учитываются: они не говорят о качестве совпадения.</li>
            <li>Логистическая регрессия оценивает, какие факторы реально влияют на согласие. Новые веса смешиваются с экспертными пропорционально объёму данных.</li>
            <li>Качество проверяется на отложенной выборке (ROC-AUC) — веса меняются, только если стало лучше.</li>
          </ul>
          {res && (
            <div className="mt-4 rounded-xl bg-plum-50 p-4 text-sm">
              {res.note ? res.note : <>Примеров: <b>{res.n}</b>, доверие к данным: {res.alpha}. ROC-AUC на отложенной выборке: экспертные веса <b>{res.auc_holdout_default}</b>, новые <b>{res.auc_holdout_new}</b>.</>}
            </div>
          )}
        </Panel>
      </div>
      {data.models.length > 0 && (
        <Panel title="История моделей" className="mt-6">
          <div className="divide-y divide-mist text-sm">
            {data.models.map((m: any) => (
              <div key={m.id} className="flex flex-wrap items-center gap-3 py-2">
                <span className="w-36">{dateRu(m.created_at)}</span><span>примеров: {m.n_samples}</span>
                <span>AUC: {m.metrics.auc_holdout_default} → {m.metrics.auc_holdout_new}</span>{m.active && <Chip tone="ok">активна</Chip>}
              </div>
            ))}
          </div>
        </Panel>
      )}
    </>
  );
}
