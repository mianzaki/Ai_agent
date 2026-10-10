import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Volvox AI — Voice agents for your business",
  description: "Configure and manage your Volvox AI voice agents.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
