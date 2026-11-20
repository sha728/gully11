import type { Metadata } from "next";
import { Big_Shoulders, Instrument_Sans, JetBrains_Mono } from "next/font/google";
import { SearchPaletteProvider } from "@/components/search-palette";
import { SiteHeader, Wordmark } from "@/components/site-header";
import { themeScript } from "@/components/theme-toggle";
import { TooltipProvider } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import "./globals.css";

// No metric overrides exist for Big Shoulders, so skip the generated fallback (avoids a build warning).
const display = Big_Shoulders({ subsets: ["latin"], weight: ["600", "700", "800", "900"], variable: "--font-shoulders", adjustFontFallback: false });
const sans = Instrument_Sans({ subsets: ["latin"], variable: "--font-instrument" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains" });

// Hosted on free plans, the API sleeps when idle and takes about a minute to wake:
// let server-rendered pages wait for it (60 s is Vercel Hobby's ceiling).
export const maxDuration = 60;

export const metadata: Metadata = {
  title: { default: "Gully11 — cricket, ball by ball", template: "%s — Gully11" },
  description:
    "Career and season numbers, phase splits, head-to-heads and ground records for Tests, ODIs, T20Is and the IPL.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning className={cn(display.variable, sans.variable, mono.variable)}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-dvh">
        <TooltipProvider delayDuration={150}>
          <SearchPaletteProvider>
            <SiteHeader />
            <main className="mx-auto max-w-7xl px-4 pt-8 pb-16 sm:px-6">{children}</main>
            <footer className="border-t">
              <div className="mx-auto grid max-w-7xl gap-6 px-4 py-10 sm:px-6 md:grid-cols-[auto_1fr]">
                <Wordmark />
                <p className="max-w-3xl text-xs leading-relaxed text-muted-foreground md:justify-self-end md:text-right">
                  Ball-by-ball data from <a className="underline underline-offset-2 hover:text-foreground" href="https://cricsheet.org/">Cricsheet</a>{" "}
                  (<a className="underline underline-offset-2 hover:text-foreground" href="https://cricsheet.org/licensing/">ODC-BY</a>):
                  men&apos;s Tests from Dec 2001, ODIs from 2002, T20Is from 2005 and every IPL match. A few older
                  internationals are missing, so some career totals sit below the official ones. Names from
                  Wikidata (CC0); player details from Wikipedia (CC BY-SA 4.0).
                </p>
              </div>
            </footer>
          </SearchPaletteProvider>
        </TooltipProvider>
      </body>
    </html>
  );
}
