import Link from "next/link";
import type { CSSProperties } from "react";
import { preload } from "react-dom";
import { Icon, type IconName } from "@/components/Icon";
import { LandingStage } from "@/components/LandingStage";
import { Wordmark } from "@/components/ui";

const POINTS: { icon: IconName; label: string }[] = [
  { icon: "live", label: "Sees what's live" },
  { icon: "map", label: "Fits how you travel" },
  { icon: "shield", label: "Honest when unsure" },
];

const delay = (ms: number) => ({ "--d": `${ms}ms` }) as CSSProperties;

export default function Landing() {
  preload("/brand/wordmark.webp", { as: "image", fetchPriority: "high" });
  return (
    <LandingStage className="relative isolate flex min-h-dvh flex-col overflow-hidden">
      <noscript>
        <style>{".landing .enter, .landing .enter-logo { animation: none; }"}</style>
      </noscript>
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
        <p className="enter mt-4 max-w-[30ch] text-balance text-[19px] leading-relaxed sm:text-[21px]" style={delay(750)}>
          Every journey deserves a guardian angel.
          <span className="block text-muted">We go a step ahead, so you can simply arrive.</span>
        </p>

        <ul className="mt-10 flex w-full max-w-[460px] items-start justify-center gap-4 sm:gap-10">
          {POINTS.map((p, i) => (
            <li key={p.label} className="enter flex flex-1 flex-col items-center gap-2.5" style={delay(950 + i * 130)}>
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-bg text-brand shadow-[0_8px_24px_-10px_rgba(0,113,227,0.55)]">
                <Icon name={p.icon} className="h-[22px] w-[22px]" stroke={1.9} />
              </span>
              <span className="text-[13px] font-medium leading-tight text-muted sm:text-[14px]">{p.label}</span>
            </li>
          ))}
        </ul>

        <p className="enter mt-9 text-balance text-[17px] font-medium sm:text-[19px]" style={delay(1400)}>
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
    </LandingStage>
  );
}
