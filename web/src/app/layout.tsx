import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import SearchBox from "@/components/SearchBox";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "Gully11 · Cricket stats", template: "%s · Gully11" },
  description:
    "Player stats, head-to-head comparisons and venue records for Test, ODI, T20I and IPL cricket.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <header className="sticky top-0 z-40 border-b border-border bg-bg/90 backdrop-blur">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
            <Link href="/" className="text-lg font-semibold tracking-tight">
              <span className="text-accent">Gully</span>11
            </Link>
            <nav className="flex gap-4 text-sm text-muted">
              <Link href="/players" className="hover:text-text">Players</Link>
              <Link href="/compare" className="hover:text-text">Compare</Link>
              <Link href="/venues" className="hover:text-text">Venues</Link>
            </nav>
            <div className="ml-auto w-full sm:w-72">
              <SearchBox />
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
        <footer className="mx-auto max-w-6xl px-4 pb-10 pt-6 text-xs text-muted">
          Ball-by-ball data from{" "}
          <a className="underline" href="https://cricsheet.org/">Cricsheet</a> (
          <a className="underline" href="https://cricsheet.org/licensing/">ODC-BY</a>). Stats cover
          the matches Cricsheet records: men&apos;s Tests from Dec 2001, ODIs from 2002, T20Is from
          2005, every IPL match. Some older internationals are missing, so career totals can
          trail official figures. Player names from Wikidata (CC0); player details from
          Wikipedia (CC BY-SA 4.0).
        </footer>
      </body>
    </html>
  );
}
