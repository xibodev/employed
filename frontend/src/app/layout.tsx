import type { ReactNode } from "react";
import { headers } from "next/headers";
import { NextIntlClientProvider } from "next-intl";
import { getMessages } from "next-intl/server";

import Footer from "@/components/layout/Footer";
import Header from "@/components/layout/Header";
import { RuntimeEnvScript } from "@/components/layout/RuntimeEnvScript";
import { AuthProvider } from "@/hooks/useAuth";
import { MarketProvider } from "@/hooks/useMarket";
import { resolveMarketFromHeaders } from "@/lib/market";
import { buildMetadata } from "@/lib/seo";

import "./globals.css";

export async function generateMetadata() {
  const requestHeaders = await headers();
  const market = resolveMarketFromHeaders(requestHeaders);

  return buildMetadata({
    title: market.siteName,
    description: market.tagline,
    market,
    pathname: "/"
  });
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  const requestHeaders = await headers();
  const market = resolveMarketFromHeaders(requestHeaders);
  const messages = await getMessages();

  return (
    <html lang={market.locale}>
      <body>
        <RuntimeEnvScript />
        <NextIntlClientProvider messages={messages}>
          <MarketProvider initialMarket={market}>
            <AuthProvider>
              <div className="flex min-h-screen flex-col">
                <Header />
                <main className="flex-1 py-10">{children}</main>
                <Footer />
              </div>
            </AuthProvider>
          </MarketProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
