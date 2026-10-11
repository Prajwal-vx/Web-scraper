import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'NEXUS SCRAPE AI — Production Web Intelligence Platform',
  description: 'AI-Powered Web Scraping, JavaScript Page Hydration, and Data Intelligence Platform',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#0a0d14] text-slate-100 min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}
