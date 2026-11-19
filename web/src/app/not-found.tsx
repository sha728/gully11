import Link from "next/link";

export default function NotFoundPage() {
  return (
    <div className="py-16 text-center">
      <h1 className="text-2xl font-semibold">Not found</h1>
      <p className="mt-2 text-muted">That player or venue isn&apos;t in the records.</p>
      <Link href="/" className="mt-6 inline-block text-accent">Back to search</Link>
    </div>
  );
}
