import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import { Sidebar } from "@/components/Sidebar";
import { MockModeBanner } from "@/components/MockModeBanner";
import "./globals.css";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-plex-sans",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
});

export const metadata: Metadata = {
  title: "Compliance Remediation Console",
  description:
    "Internal Linux compliance remediation operator UI (MOCK_MODE). Excel Remediation text is never executed.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${plexSans.variable} ${plexMono.variable}`}>
        <div className="app-shell">
          <Sidebar />
          <div className="main">
            <MockModeBanner />
            <div className="content">{children}</div>
          </div>
        </div>
      </body>
    </html>
  );
}
