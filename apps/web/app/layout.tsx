import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Knowledge Platform",
  description: "Secure, cited answers from governed documents",
};

const links = [
  ["/", "Dashboard"],
  ["/chat", "Chat"],
  ["/documents", "Documents"],
  ["/ingestion", "Ingestion"],
  ["/users", "Users"],
  ["/admin", "Admin"],
] as const;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <aside className="sidebar">
          <div className="brand"><span className="brandMark">K</span><span>Knowledge</span></div>
          <nav>{links.map(([href, label]) => <Link key={href} href={href}>{label}</Link>)}</nav>
          <div className="sideFoot"><span className="healthDot" /> Platform ready<br /><Link href="/auth/logout">Sign out</Link></div>
        </aside>
        <main className="shell">{children}</main>
      </body>
    </html>
  );
}
