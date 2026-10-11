import { ExternalLink, FileText } from "lucide-react";
import { linkHref, reportHeadingTitle } from "./data";
import type { ResourceLink, Roadmap } from "./types";
import type { ReactNode } from "react";

export function Header({ roadmap, title, actions }: { roadmap: Roadmap; eyebrow?: string; title: string; actions?: ReactNode }) {
  return <header className="app-header"><h1>{reportHeadingTitle(roadmap, title)}</h1>{actions}</header>;
}
export function ResourceButton({ item, label }: { item?: ResourceLink; label?: string }) {
  const href = linkHref(item);
  if (!href) return null;
  const text = label || item?.label || item?.title || "Open source";
  return <a className="resource-link" href={href} title={item?.title || text}>
    {item?.local_href && href === item.local_href ? <FileText size={15} /> : <ExternalLink size={15} />}<span>{text}</span>
  </a>;
}
export function Empty({ children }: { children: ReactNode }) { return <p className="empty-state">{children}</p>; }
