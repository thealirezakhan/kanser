import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

const pjs = Plus_Jakarta_Sans({
  variable: "--font-pjs",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
});

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });

const jetbrains = JetBrains_Mono({ variable: "--font-jetbrains", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "KANser — Clinical AI",
  description: "Multimodal lung cancer agentic AI diagnosis platform",
};

const MATERIAL_SYMBOLS =
  "https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap";

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${pjs.variable} ${inter.variable} ${jetbrains.variable} h-full antialiased`}
    >
      <head>
        <link rel="stylesheet" href={MATERIAL_SYMBOLS} />
      </head>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
