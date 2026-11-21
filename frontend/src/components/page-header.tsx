export function PageHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="mb-7">
      <h1 className="text-[28px] font-bold tracking-[-0.035em] sm:text-[32px]">{title}</h1>
      <p className="mt-2 max-w-prose text-[13px] leading-relaxed text-mist-300">{description}</p>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="rounded-lg border border-dashed border-ink-700 p-8">
      <p className="font-medium">{title}</p>
      <p className="mt-1 text-sm text-mist-300">{hint}</p>
    </div>
  );
}
