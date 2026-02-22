import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { AccountProvider } from "@/lib/AccountContext";

export const metadata: Metadata = {
  title: "Gmail Cleaner",
  description: "Personal Gmail storage cleanup tool",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased flex min-h-screen bg-gray-50 text-gray-900">
        <AccountProvider>
          <Sidebar />
          <main className="flex-1 overflow-auto">{children}</main>
        </AccountProvider>
      </body>
    </html>
  );
}
