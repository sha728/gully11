"use client";

import { MoonIcon, SunIcon } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

/** Runs before paint (inlined in <head>) so the page never flashes the wrong theme. */
export const themeScript = `(() => {
  try {
    const saved = localStorage.getItem("theme");
    const dark = saved ? saved === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.classList.toggle("dark", dark);
  } catch (_) {}
})();`;

export function ThemeToggle() {
  const [dark, setDark] = useState<boolean | null>(null);
  useEffect(() => setDark(document.documentElement.classList.contains("dark")), []);

  function toggle() {
    const next = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("theme", next ? "dark" : "light");
    } catch {}
    setDark(next);
  }

  return (
    <Button variant="ghost" size="icon" onClick={toggle} aria-label={dark ? "Switch to light" : "Switch to dark"}>
      {dark ? <SunIcon /> : <MoonIcon />}
    </Button>
  );
}
