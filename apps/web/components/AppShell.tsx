"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AccountMenu } from "./AccountMenu";
import { Icon, type IconName } from "./Icon";
import { AppLogo } from "./ui";

type Tab = { href: string; label: string; icon: IconName };

const VISITOR_TABS: Tab[] = [
  { href: "/plan", label: "Plan", icon: "map" },
  { href: "/answer", label: "Answer", icon: "answer" },
  { href: "/live", label: "Live", icon: "live" },
  { href: "/report", label: "Report", icon: "message" },
];

const STAFF_TABS: Tab[] = [
  { href: "/staff/check", label: "Daily check", icon: "checklist" },
  { href: "/staff/alerts", label: "Alerts", icon: "bell" },
  { href: "/staff/listing", label: "Listing", icon: "shield" },
  { href: "/staff/demo", label: "Demo", icon: "sliders" },
];

const isActive = (path: string, href: string) => path === href || path.startsWith(href + "/");

function SidebarLink({ tab, active }: { tab: Tab; active: boolean }) {
  return (
    <Link
      href={tab.href}
      aria-current={active ? "page" : undefined}
      className={`tap flex items-center gap-3 rounded-[12px] px-3 text-[15px] font-medium transition-colors ${
        active ? "bg-fill text-white" : "text-ink hover:bg-card2"
      }`}
    >
      <Icon name={tab.icon} className={`h-[22px] w-[22px] ${active ? "" : "text-brand"}`} />
      {tab.label}
    </Link>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname() || "/";
  const staff = path.startsWith("/staff");
  const tabs = staff ? STAFF_TABS : VISITOR_TABS;

  return (
    <div className="min-h-dvh">
      <a href="#main" className="sr-only-focusable fixed left-3 top-3 z-[60] rounded-full bg-fill px-4 py-2 font-semibold text-white">
        Skip to content
      </a>

      {/* Sidebar: tablet and desktop */}
      <aside className="glass fixed inset-y-0 left-0 z-40 hidden w-[272px] flex-col border-r border-line md:flex">
        <Link href="/plan" className="tap mx-3 mt-5 flex items-center gap-3 rounded-[14px] px-2">
          <AppLogo size={36} />
          <span className="text-[22px] font-bold tracking-tight">Ecstasy</span>
        </Link>
        <nav aria-label="Main" className="mt-6 flex-1 space-y-6 overflow-y-auto px-3">
          <div>
            <h2 className="px-3 pb-1.5 text-[13px] font-semibold uppercase tracking-wide text-muted">Visitor</h2>
            <div className="space-y-0.5">{VISITOR_TABS.map((t) => <SidebarLink key={t.href} tab={t} active={isActive(path, t.href)} />)}</div>
          </div>
          <div>
            <h2 className="px-3 pb-1.5 text-[13px] font-semibold uppercase tracking-wide text-muted">Venue staff</h2>
            <div className="space-y-0.5">{STAFF_TABS.map((t) => <SidebarLink key={t.href} tab={t} active={isActive(path, t.href)} />)}</div>
          </div>
        </nav>
        <div className="border-t border-line p-3 pb-5">
          <AccountMenu placement="up" />
        </div>
      </aside>

      {/* Top bar: phones */}
      <header className="glass sticky top-0 z-30 border-b border-line pt-[env(safe-area-inset-top)] md:hidden">
        <div className="flex h-14 items-center justify-between gap-2 px-4">
          <Link href={staff ? "/staff/check" : "/plan"} className="tap flex items-center gap-2.5">
            <AppLogo size={30} />
            <span className="text-[19px] font-bold tracking-tight">Ecstasy</span>
            {staff && <span className="badge bg-ink px-2 py-0.5 text-[11px] uppercase tracking-wide text-bg">Staff</span>}
          </Link>
          <AccountMenu />
        </div>
      </header>

      <main id="main" className="md:pl-[272px]">
        <div className="mx-auto w-full max-w-[1120px] px-4 pb-36 pt-5 sm:px-6 md:px-10 md:pb-16 md:pt-12">{children}</div>
      </main>

      {/* Floating tab bar: phones */}
      <nav
        aria-label={staff ? "Staff sections" : "Visitor sections"}
        className="pointer-events-none fixed inset-x-0 bottom-0 z-30 flex justify-center px-4 pb-[calc(env(safe-area-inset-bottom)+12px)] md:hidden"
      >
        <ul className="glass pointer-events-auto grid w-full max-w-[420px] grid-cols-4 gap-1 rounded-full border border-line p-1.5 shadow-[0_12px_40px_-12px_rgba(0,0,0,0.35)]">
          {tabs.map((t) => {
            const active = isActive(path, t.href);
            return (
              <li key={t.href}>
                <Link
                  href={t.href}
                  aria-current={active ? "page" : undefined}
                  className={`flex min-h-[52px] flex-col items-center justify-center gap-0.5 rounded-full text-[11px] font-semibold transition-colors ${
                    active ? "bg-brand-bg text-brand" : "text-muted"
                  }`}
                >
                  <Icon name={t.icon} className="h-[22px] w-[22px]" stroke={active ? 2.2 : 1.8} />
                  <span>{t.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
