import type { Metadata, Viewport } from "next";
import "@fontsource-variable/anek-latin/wdth.css";
import "@fontsource-variable/anek-devanagari/wdth.css";
import "@fontsource-variable/anek-tamil/wdth.css";
import "@fontsource-variable/anek-bangla/wdth.css";
import "@fontsource-variable/anek-telugu/wdth.css";
import "@fontsource-variable/anek-kannada/wdth.css";
import "@fontsource-variable/anek-malayalam/wdth.css";
import "@fontsource-variable/anek-gujarati/wdth.css";
import "@fontsource-variable/anek-gurmukhi/wdth.css";
import "@fontsource-variable/anek-odia/wdth.css";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { themeBootScript } from "@/lib/theme";

export const metadata: Metadata = {
  title: "Akshara",
  description: "Ask your documents questions in English and 22 Indian languages, with cited answers.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fcfcfe" },
    { media: "(prefers-color-scheme: dark)", color: "#131531" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootScript }} />
      </head>
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
