import type { Metadata } from "next";
import { Inter, Poppins } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const poppins = Poppins({
  variable: "--font-poppins",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "MarketPulse — Competitive Intelligence",
  description: "AI-powered competitive intelligence briefings for strategy teams",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${poppins.variable} h-full`}
    >
      <body className="min-h-full flex antialiased" style={{ background: "#EFE6D8" }}>
        <Sidebar />
        <main className="flex-1 min-h-screen overflow-y-auto p-6 lg:p-8">
          {children}
        </main>
      </body>
    </html>
  );
}
