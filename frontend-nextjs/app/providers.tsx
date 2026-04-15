'use client'

import { Toaster } from 'react-hot-toast'

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <>
      {children}
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: '#1e1e1e',
            color: '#f0f0f0',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: '12px',
            fontSize: '13px',
            fontFamily: 'Inter, sans-serif',
          },
          success: { iconTheme: { primary: '#2ed573', secondary: '#0e0e0e' } },
          error: { iconTheme: { primary: '#ff4757', secondary: '#0e0e0e' } },
        }}
      />
    </>
  )
}
