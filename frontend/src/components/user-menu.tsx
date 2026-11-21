"use client";
import Link from "next/link";
import { UserRound } from "lucide-react";
import { useAuth } from "@/components/providers";
export function UserMenu() {
  const { user,loading,configured } = useAuth();
  if (!configured || loading) return null;
  return <Link href={user ? "/settings" : "/auth/login"} aria-label={user ? "Tài khoản của bạn" : "Đăng nhập"} className="inline-flex h-10 items-center gap-2.5 rounded-full border border-white/[0.07] bg-ink-800/50 p-1.5 pr-1.5 text-xs text-mist-100 hover:border-lime-500/50 sm:pr-3"><span className="grid size-7 place-items-center rounded-full bg-[#393044] text-[11px] font-bold text-lime-300">{user?.email ? user.email.charAt(0).toUpperCase() : <UserRound size={14}/>}</span><span className="hidden max-w-[160px] truncate sm:inline">{user ? (user.email ?? "Tài khoản") : "Đăng nhập"}</span></Link>;
}
