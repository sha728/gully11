"use client";

import { ListIcon } from "@phosphor-icons/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { SearchTrigger } from "@/components/search-palette";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/players", label: "Players" },
  { href: "/compare", label: "Head to head" },
  { href: "/xi", label: "XI Builder" },
  { href: "/auction", label: "Auction" },
  { href: "/venues", label: "Grounds" },
];

export function Wordmark() {
  return (
    <Link href="/" className="group flex items-center gap-2" aria-label="Gully11 home">
      {/* a ball with its seam */}
      <span className="relative grid size-5 place-items-center rounded-full bg-signal">
        <span className="absolute inset-y-0.5 w-px border-l border-dashed border-signal-foreground/70" />
      </span>
      <span className="font-display text-2xl leading-none font-extrabold tracking-tight uppercase">
        Gully<span className="text-signal">11</span>
      </span>
    </Link>
  );
}

export function SiteHeader() {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const active = (href: string) => path === href || path.startsWith(href + "/");
  return (
    <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4 sm:px-6">
        <Wordmark />
        <nav className="hidden items-center gap-1 md:flex">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={cn(
                "relative px-2.5 py-1.5 font-mono text-xs tracking-wide uppercase transition-colors",
                active(n.href) ? "text-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {n.label}
              {active(n.href) && <span className="absolute inset-x-2.5 -bottom-[13px] h-0.5 bg-signal" />}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <SearchTrigger className="hidden w-64 sm:flex" />
          <ThemeToggle />
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="md:hidden" aria-label="Menu"><ListIcon /></Button>
            </SheetTrigger>
            <SheetContent side="right" className="w-72">
              <SheetHeader><SheetTitle className="sr-only">Menu</SheetTitle><Wordmark /></SheetHeader>
              <div className="grid gap-1 px-4">
                <SearchTrigger className="mb-3" />
                {NAV.map((n) => (
                  <Link key={n.href} href={n.href} onClick={() => setOpen(false)}
                    className={cn("border-l-2 px-3 py-2 font-mono text-sm uppercase",
                      active(n.href) ? "border-signal text-foreground" : "border-transparent text-muted-foreground")}>
                    {n.label}
                  </Link>
                ))}
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
}
