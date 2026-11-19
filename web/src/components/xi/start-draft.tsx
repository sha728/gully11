"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { XI_COPY, xiApi, type XIFormat } from "@/lib/xi";

export function StartDraft({ format, seed, daily, vs }: { format: XIFormat; seed?: number; daily: boolean; vs?: string }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;          // dev StrictMode runs effects twice
    started.current = true;
    xiApi.newDraft(format, { seed, daily, vs })
      .then((d) => router.replace(`/xi/d/${d.id}`))
      .catch((e) => setError(e instanceof Error ? e.message : "Couldn't start a draft."));
  }, [format, seed, daily, vs, router]);

  return (
    <div className="grid min-h-[50vh] place-items-center text-center">
      <div className="space-y-4">
        <div className="label">{XI_COPY[format].title} · {daily ? "today's challenge" : seed !== undefined ? `draw #${seed}` : "random draw"}</div>
        {error ? (
          <>
            <p className="text-destructive">{error}</p>
            <Button asChild variant="outline"><Link href="/xi">Back to XI Builder</Link></Button>
          </>
        ) : (
          <p className="font-display text-4xl font-black uppercase">Shuffling the eras…</p>
        )}
      </div>
    </div>
  );
}
