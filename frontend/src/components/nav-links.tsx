"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV_ITEMS } from "@/lib/nav";
import { AudioLines, ArrowUpRight, Headphones, Settings } from "lucide-react";

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="app-sidebar hidden w-[228px] shrink-0 flex-col border-r border-white/[0.06] bg-[#131317] px-4 py-7 md:flex">
      <Link href="/" className="mb-11 flex items-center gap-3 px-3" aria-label="Music Discovery Việt Nam — Trang chủ">
        <span className="grid size-10 shrink-0 place-items-center rounded-[14px] bg-lime-400 text-ink-950"><AudioLines size={24} strokeWidth={2.3} /></span>
        <span><span className="block text-[15px] font-bold tracking-tight">Music Discovery<span className="text-lime-400">.</span></span><span className="mt-0.5 block text-[10px] tracking-[.25em] text-mist-400">VIỆT NAM</span></span>
      </Link>
      <p className="eyebrow mb-4 px-4 text-mist-400">Không gian của bạn</p>
      <nav aria-label="Điều hướng chính" className="flex flex-col gap-2">
        {NAV_ITEMS.filter(item => item.href !== "/settings").map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`relative flex items-center gap-3 rounded-xl px-4 py-3 text-[13px] font-medium transition-colors ${
                active ? "bg-lime-400/[0.10] text-lime-300" : "text-mist-300 hover:bg-white/[0.04] hover:text-mist-100"
              }`}
            >
              <Icon size={19} strokeWidth={active ? 2.2 : 1.7} aria-hidden /> {label}
              {active && <span className="ml-auto size-1.5 rounded-full bg-lime-400" aria-hidden />}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto space-y-5 pt-8">
        <Link href="/identify" className="group block rounded-2xl border border-white/[0.06] bg-gradient-to-br from-[#282232] to-[#1c1b23] p-4">
          <Headphones size={22} className="mb-4 text-lime-400" />
          <p className="text-sm font-semibold">Giai điệu nào vậy?</p>
          <p className="mt-2 text-xs leading-relaxed text-mist-300">Tìm tên bài hát đang vang lên quanh bạn.</p>
          <span className="mt-4 inline-flex items-center gap-2 text-[11px] font-semibold text-lime-300">Thử nhận diện <ArrowUpRight size={13} className="transition group-hover:translate-x-0.5" /></span>
        </Link>
        <Link href="/settings" aria-current={pathname === "/settings" ? "page" : undefined} className={`flex items-center gap-3 rounded-xl px-4 py-3 text-[13px] ${pathname === "/settings" ? "bg-lime-400/10 text-lime-300" : "text-mist-400 hover:bg-ink-800 hover:text-mist-100"}`}><Settings size={18} />Tài khoản</Link>
      </div>
    </aside>
  );
}

export function BottomNav() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Điều hướng chính"
      className="mobile-nav fixed inset-x-0 z-20 flex justify-around border-t border-white/[0.06] bg-ink-900/95 backdrop-blur-xl md:hidden"
    >
      {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={`flex min-w-0 flex-1 flex-col items-center gap-1 py-3 text-[10px] ${
              active ? "text-lime-400" : "text-mist-300"
            }`}
          >
            <Icon size={20} aria-hidden /> {label}
          </Link>
        );
      })}
    </nav>
  );
}
