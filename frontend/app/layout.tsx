import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Policy desk · Review workspace",
  description:
    "Review synthetic insurance policy requests, supporting evidence, and proposed contact updates.",
};
export default function Layout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
