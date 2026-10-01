import Link from "next/link";
import type { CSSProperties } from "react";
import { Icon, type IconName } from "@/components/Icon";
import { Wordmark } from "@/components/ui";

const POINTS: { icon: IconName; title: string; text: string }[] = [
  { icon: "live", title: "Live, not last year's listing", text: "Lifts, gates and paths as they are right now." },
  { icon: "map", title: "Fits how you travel", text: "Your chair, your pace and your needs, every visit." },
  { icon: "shield", title: "Honest when unsure", text: "Every answer shows where it came from." },
];

const delay = (ms: number) => ({ "--d": `${ms}ms` }) as CSSProperties;

export default function Landing() {
  return (
    <div className="relative isolate flex min-h-dvh flex-col overflow-hidden">
      <div aria-hidden="true" className="landing-glow float-slow left-[-18%] top-[-14%] h-[55vmax] w-[55vmax] bg-[#3d8bff]" />
      <div aria-hidden="true" className="landing-glow float-slow bottom-[-24%] right-[-16%] h-[50vmax] w-[50vmax] bg-[#8cc2ff] [animation-delay:-4.5s]" />

      <main
        id="main"
        className="relative mx-auto flex w-full max-w-[720px] flex-1 flex-col items-center justify-center px-6 pb-[calc(env(safe-area-inset-bottom)+40px)] pt-[calc(env(safe-area-inset-top)+48px)] text-center"
      >
        <h1 className="float-slow w-full">
          <Wordmark priority className="enter-logo mx-auto w-[min(84vw,540px)]" />
        </h1>

        <p className="enter mt-5 text-[22px] font-semibold tracking-tight sm:text-[26px]" style={delay(550)}>
          Accessible until the last staircase.
        </p>
        <p className="enter mt-3 max-w-[36ch] text-[17px] leading-relaxed text-muted sm:text-[19px]" style={delay(750)}>
          Ecstasy checks a venue&rsquo;s lifts, gates and paths as they are right now, and tells you honestly whether you can
          get from the door to your seat.
        </p>

        <ul className="mt-9 grid w-full gap-3 text-left sm:grid-cols-3">
          {POINTS.map((p, i) => (
            <li key={p.title} className="enter glass flex items-start gap-3 rounded-[22px] border border-line p-4 sm:block" style={delay(950 + i * 130)}>
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-bg text-brand">
                <Icon name={p.icon} className="h-5 w-5" stroke={2} />
              </span>
              <div className="sm:mt-3">
                <p className="text-[15px] font-semibold leading-snug">{p.title}</p>
                <p className="mt-0.5 text-[14px] leading-snug text-muted">{p.text}</p>
              </div>
            </li>
          ))}
        </ul>

        <p className="enter mt-9 text-[17px] font-medium sm:text-[19px]" style={delay(1400)}>
          Wherever you&rsquo;re headed, we&rsquo;re here for you, friend.
        </p>

        <div className="enter mt-6 flex w-full flex-col items-stretch gap-3 sm:flex-row sm:justify-center" style={delay(1550)}>
          <Link href="/plan" className="btn btn-primary px-8">
            Plan my visit
          </Link>
          <Link href="/settings" className="btn btn-tinted min-h-[52px] px-6">
            Set up my travel profile
          </Link>
        </div>
        <Link href="/staff/check" className="enter tap mt-3 inline-flex items-center justify-center text-[15px] font-medium text-brand" style={delay(1700)}>
          I work at a venue
        </Link>
      </main>
    </div>
  );
}
