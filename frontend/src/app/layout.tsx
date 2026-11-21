import type { Metadata } from "next";
import "./globals.css";
import { Sidebar, BottomNav } from "@/components/nav-links";
import { TopBar } from "@/components/top-bar";
import { PlayerBar } from "@/components/player-bar";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "Music Discovery Vietnam",
  description: "Tìm kiếm, nhận diện và khám phá âm nhạc.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body>
        <Providers>
        <div className="flex min-h-screen">
          <Sidebar />
          <div className="flex min-w-0 flex-1 flex-col">
            <TopBar />
            <main id="main-content" className="app-main flex-1">{children}</main>
          </div>
        </div>
        <BottomNav />
        <PlayerBar />
        </Providers>
      </body>
    </html>
  );
}
