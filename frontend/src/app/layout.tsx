import type { Metadata } from "next";
import { Roboto } from "next/font/google";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

const roboto = Roboto({
  subsets: ["latin", "vietnamese"],
  weight: ["100", "300", "400", "500", "700", "900"],
  style: ["normal", "italic"],
  variable: "--font-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "CMD Support — Trợ lý Tư vấn KHDN BIDV",
  description:
    "Hệ thống quản lý tri thức và tư vấn khách hàng doanh nghiệp BIDV",
  icons: {
    icon: [
      { url: "/bidv-logo.webp", type: "image/webp" },
    ],
    shortcut: "/bidv-logo.webp",
    apple: "/bidv-logo.webp",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi" className={roboto.variable}>
      <head>
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap"
        />
      </head>
      <body>
        <AuthProvider>
          <TooltipProvider>{children}</TooltipProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
