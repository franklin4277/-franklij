import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "问数 Agent · Data Agent",
  description: "基于 SQLBot 的自然语言数据查询",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}