import type { Metadata } from "next";
import { Inter, Poppins } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
// PHASE 5 ADDITION — multi-tenant auth pilot wrapper (off by default).
// When ENABLE_MULTI_TENANT_AUTH=false this is a pure pass-through.
import { AuthPilotWrapper } from "@/components/AuthPilotWrapper";

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
      <body className="min-h-full flex antialiased" style={{ background: "#EFE6D8", color: "#2E2A22" }}>
        <Sidebar />
        {/* PHASE 5: AuthPilotWrapper is a pass-through when pilot is off */}
        <AuthPilotWrapper>
          <main className="flex-1 min-h-screen overflow-y-auto p-6 lg:p-10">
            {children}
          </main>
        </AuthPilotWrapper>
      </body>
    </html>
  );
}
