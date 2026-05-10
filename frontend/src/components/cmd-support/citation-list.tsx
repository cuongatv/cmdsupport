"use client";

import Link from "next/link";

type Citation = {
  wiki_slug: string;
  title: string;
  source_ids: string[];
};

type Props = {
  citations: Citation[];
};

export function CitationList({ citations }: Props) {
  if (!citations || citations.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {citations.map((c, i) => (
        <Link
          key={`${c.wiki_slug}-${i}`}
          href={`/admin/wiki/${c.wiki_slug}`}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-primary/5 text-xs text-primary hover:bg-primary/10 transition-colors"
        >
          <span className="material-symbols-outlined text-xs">article</span>
          {c.title}
        </Link>
      ))}
    </div>
  );
}
