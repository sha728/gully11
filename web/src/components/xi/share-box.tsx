"use client";

import { CheckIcon, CopyIcon } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** Copyable challenge link: friends draft from the same spins and try to beat you. */
export function ShareBox({ path }: { path: string }) {
  const [url, setUrl] = useState(path);
  const [copied, setCopied] = useState(false);
  useEffect(() => setUrl(window.location.origin + path), [path]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard can be blocked; the field is selectable as a fallback.
    }
  }

  return (
    <div className="flex gap-2">
      <Input readOnly value={url} onFocus={(e) => e.currentTarget.select()} className="h-10 font-mono text-xs" />
      <Button onClick={copy} variant="secondary" className="h-10 shrink-0">
        {copied ? <><CheckIcon />Copied</> : <><CopyIcon />Copy</>}
      </Button>
    </div>
  );
}
