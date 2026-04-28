import type { Metadata } from "next";
import "../styles/globals.css";

export const metadata: Metadata = {
  title: "PirateHunt Dashboard",
  description: "Real-time live-stream piracy detection",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-slate-950 text-slate-100 font-sans">
        <div className="min-h-screen">
          {children}
        </div>
      </body>
    </html>
  );
}
