import { cleanHeaderSubtitle, compactTitle, linkHref, targetPaperTitle } from "./data";
import type { ResourceLink, Roadmap } from "./types";
import type { ReactNode } from "react";

export function Header({
  roadmap,
  eyebrow,
  title,
  actions,
}: {
  roadmap: Roadmap;
  eyebrow: string;
  title: string;
  actions?: ReactNode;
}) {
  const targetTitle = targetPaperTitle(roadmap);
  const subtitle = cleanHeaderSubtitle(cleanHeaderSubtitle(roadmap.profile?.goal || roadmap.title, title), targetTitle);
  return (
    <header className="app-header">
      <div className="min-w-0">
        <p className="eyebrow">{eyebrow}</p>
        <h1>{compactTitle(title, 84)}</h1>
        <p className="subtle">{compactTitle(subtitle, 130)}</p>
      </div>
      {actions ? <nav className="header-actions">{actions}</nav> : null}
    </header>
  );
}

export function ResourceButton({ item, label }: { item?: ResourceLink; label?: string }) {
  const href = linkHref(item);
  if (!href) return null;
  const text = label || item?.label || item?.title || "打开资料";
  return (
    <a className="pill-link" href={href} title={text}>
      {compactTitle(text, 54)}
    </a>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty-state">{children}</p>;
}
