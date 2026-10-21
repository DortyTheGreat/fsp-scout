"use client";
import Link from "next/link";
import { Logo } from "@/components/shell";
import { LevelScale, ScoreBar } from "@/components/domain";
import { Button, Chip } from "@/components/ui";
import { useSession } from "@/lib/session";

const CANDIDATE_STEPS = [
  ["Расскажите о себе", "Короткий опрос: направление, специализация, уровень, на который претендуете. Резюме можно загрузить в PDF — поля заполнятся сами."],
  ["Пройдите тест на свой грейд", "20–30 минут. Вопросы подстраиваются под ваши ответы, у каждого кандидата свои варианты заданий."],
  ["Получите категорию", "Например, «Бэкенд-разработка, Middle». Её видят работодатели — вместе с оценками навыков и достижениями ФСП."],
  ["Отвечайте на приглашения", "Компания пишет первой и сразу указывает зарплату. Контакты откроются только тем, чьё приглашение вы примете."],
];
const EMPLOYER_STEPS = [
  ["Опишите, кто нужен", "Своими словами: стек, задачи, грейд, вилка. Система разберёт текст в требования, их можно поправить."],
  ["Выберите категорию", "Покажем, в каких категориях есть подходящие люди, сколько их и каковы их зарплатные ожидания."],
  ["Сравните кандидатов", "Каждое место в выдаче объяснено: какие навыки подтверждены тестом, что подтверждает ФСП, чего не хватает."],
  ["Пригласите конкретного человека", "Предложение с вилкой и способом связи. Статус видно сразу: просмотрено, принято или отклонено с причиной."],
];

export default function Landing() {
  const { user } = useSession();
  const home = user ? (user.role === "admin" ? "/admin" : `/${user.role}`) : null;
  return (
    <div className="min-h-screen bg-white">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-8">
        <Logo />
        <nav className="flex items-center gap-2">
          {home ? <Button href={home} variant="plum" size="sm">В личный кабинет</Button> : (
            <>
              <Button href="/login" variant="ghost" size="sm">Войти</Button>
              <Button href="/register" variant="plum" size="sm">Регистрация</Button>
            </>
          )}
        </nav>
      </header>

      <section className="mx-auto grid max-w-6xl items-center gap-10 px-4 pb-16 pt-6 sm:px-8 lg:grid-cols-[1.05fr_1fr] lg:pt-12">
        <div>
          <h1 className="text-[40px] font-extrabold leading-[1.05] sm:text-[56px]">Работодатели приходят к вам сами</h1>
          <p className="mt-5 max-w-xl text-lg leading-relaxed text-ink/70">
            Пройдите адаптивный тест и получите подтверждённую категорию. Компании видят ваш уровень, навыки
            и достижения ФСП — и присылают приглашение с зарплатой ещё до первого разговора.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button href="/register?role=candidate" size="lg">Я ищу работу</Button>
            <Button href="/register?role=employer" size="lg" variant="secondary">Я ищу специалистов</Button>
          </div>
          <p className="mt-5 text-sm text-ink/55">Спецтрек Федерации спортивного программирования, ЛЦТ 2026</p>
        </div>

        <div className="relative">
          <div className="absolute -inset-3 -z-10 rounded-[28px] bg-plum" aria-hidden />
          <div className="rounded-2xl bg-white p-6 sm:p-7">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm text-ink/55">Категория по результатам теста</div>
                <div className="mt-1 text-2xl font-extrabold text-plum">Бэкенд-разработка, Middle</div>
              </div>
              <Chip tone="signal" className="shrink-0 whitespace-nowrap">ФСП: 2 место из 80</Chip>
            </div>
            <LevelScale theta={0.55} se={0.24} current="middle" target="middle" />
            <div className="mt-5 space-y-2.5">
              {[["Python", 81], ["SQL", 74], ["PostgreSQL", 69], ["Docker", 63]].map(([n, v]) => (
                <div key={n} className="flex items-center gap-3 text-sm">
                  <span className="w-24 font-semibold">{n}</span>
                  <div className="flex-1"><ScoreBar value={Number(v)} /></div>
                  <span className="w-8 text-right font-bold tabular-nums text-plum">{v}</span>
                </div>
              ))}
            </div>
            <div className="mt-6 rounded-xl border border-signal/25 bg-signal-50 p-4">
              <div className="text-sm font-bold text-signal-600">Новое приглашение</div>
              <div className="mt-1 font-semibold">Middle Python-разработчик в платёжный шлюз</div>
              <div className="mt-0.5 text-sm text-ink/65">ТехноПлатформа, 280–340 тыс. ₽, гибрид</div>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-mist-50 py-16">
        <div className="mx-auto grid max-w-6xl gap-12 px-4 sm:px-8 lg:grid-cols-2">
          {[["Кандидату", CANDIDATE_STEPS, "/register?role=candidate", "Пройти тест"],
            ["Работодателю", EMPLOYER_STEPS, "/register?role=employer", "Начать подбор"]].map(([title, steps, href, cta]) => (
            <div key={title as string}>
              <h2 className="text-2xl font-extrabold">{title as string}</h2>
              <ol className="mt-6 space-y-5">
                {(steps as string[][]).map(([h, t], i) => (
                  <li key={h} className="flex gap-4">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-plum text-sm font-bold text-white">{i + 1}</span>
                    <div>
                      <div className="font-bold text-plum">{h}</div>
                      <p className="mt-1 text-[15px] leading-relaxed text-ink/70">{t}</p>
                    </div>
                  </li>
                ))}
              </ol>
              <Button href={href as string} variant="plum" className="mt-7">{cta as string}</Button>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-8">
        <h2 className="max-w-2xl text-2xl font-extrabold">Почему результату теста можно доверять</h2>
        <div className="mt-8 grid gap-8 md:grid-cols-3">
          <div>
            <h3 className="font-bold">Ответы не утекают</h3>
            <p className="mt-2 text-[15px] leading-relaxed text-ink/70">Каждое задание собирается из шаблона заново: другие числа, код и данные. Слитый ответ к чужому варианту не подходит.</p>
          </div>
          <div>
            <h3 className="font-bold">Сложность одинаковая для всех</h3>
            <p className="mt-2 text-[15px] leading-relaxed text-ink/70">Варианты одного шаблона решаются одинаково, а трудность шаблона откалибрована по ответам тысяч прохождений.</p>
          </div>
          <div>
            <h3 className="font-bold">Тест подстраивается под вас</h3>
            <p className="mt-2 text-[15px] leading-relaxed text-ink/70">Следующий вопрос выбирается по предыдущим ответам. Тест заканчивается, когда уровень определён уверенно, — обычно за 15–25 заданий; если результат у самой границы грейда — до 35.</p>
          </div>
        </div>
      </section>

      <section className="bg-signal-50/60">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-8">
          <h2 className="max-w-2xl text-2xl font-extrabold">Достижения ФСП — сильнее, когда они про вашу задачу</h2>
          <p className="mt-3 max-w-3xl text-[15px] leading-relaxed text-ink/70">
            Результаты соревнований Федерации спортивного программирования приходят из реестра с подписью и проверяются автоматически.
            Они не заменяют тест, но поднимают кандидата внутри категории — и тем выше, чем сильнее результат и чем точнее он
            подтверждает навыки, которые нужны работодателю.
          </p>
          <div className="mt-8 grid gap-8 md:grid-cols-3">
            <div>
              <h3 className="font-bold">Сила результата</h3>
              <p className="mt-2 text-[15px] leading-relaxed text-ink/70">Уровень соревнования, место с упором на призовые, размер поля и свежесть. Второе место из 120 на всероссийских весит в разы больше середины регионального этапа.</p>
            </div>
            <div>
              <h3 className="font-bold">Под конкретный запрос</h3>
              <p className="mt-2 text-[15px] leading-relaxed text-ink/70">Стек решения, дисциплина и роль в команде показывают, какие навыки подтверждает результат. Хакатон на Python и PostgreSQL поднимает кандидата под бэкенд на Python, а не под фронтенд.</p>
            </div>
            <div>
              <h3 className="font-bold">Без истории ФСП — без штрафа</h3>
              <p className="mt-2 text-[15px] leading-relaxed text-ink/70">Категорию определяет тест, поэтому кандидат без соревнований проходит тот же путь и стоит в выдаче по своим навыкам.</p>
            </div>
          </div>
        </div>
      </section>

      <footer className="bg-plum py-8 text-sm text-white/70">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 sm:px-8">
          <Logo light />
          <span>Команда «veni vidi vivii», 2026. <Link href="/api/docs" className="underline">Документация API</Link></span>
        </div>
      </footer>
    </div>
  );
}
