import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFoundPage() {
  return (
    <div className="grid place-items-center py-24 text-center">
      <div className="font-display text-[9rem] leading-none font-black text-signal">0</div>
      <div className="label mt-2">Out first ball</div>
      <h1 className="mt-4 font-display text-4xl font-extrabold uppercase">Not in the scorebook</h1>
      <p className="mt-2 text-sm text-muted-foreground">That player or ground isn&apos;t in the records.</p>
      <Button asChild className="mt-6"><Link href="/">Back to the middle</Link></Button>
    </div>
  );
}
