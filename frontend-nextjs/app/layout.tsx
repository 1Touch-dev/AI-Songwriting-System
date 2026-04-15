import type { Metadata } from 'next'
import './globals.css'
import Providers from './providers'

export const metadata: Metadata = {
  title: 'SonicFlow Studio — AI Music Platform',
  description: 'AI Songwriting • Voice Synthesis • Music Generation',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body className="bg-background text-text-primary font-body antialiased">
        <div className="relative min-h-screen">
          {/* Ambient background glows */}
          <div
            className="pointer-events-none fixed inset-0 z-0"
            aria-hidden="true"
          >
            <div className="absolute -top-64 left-1/2 -translate-x-1/2 w-[800px] h-[500px] rounded-full opacity-10"
              style={{ background: 'radial-gradient(ellipse, #8ff5ff 0%, transparent 70%)' }} />
            <div className="absolute bottom-0 right-0 w-[600px] h-[400px] rounded-full opacity-8"
              style={{ background: 'radial-gradient(ellipse, #d277ff 0%, transparent 70%)' }} />
          </div>
          <div className="relative z-10">
            <Providers>{children}</Providers>
          </div>
        </div>
      </body>
    </html>
  )
}
