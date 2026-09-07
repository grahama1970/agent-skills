import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { TeleprompterPage } from './components/Teleprompter'
import './index.css'

const App = lazy(() => import('./App').then(module => ({ default: module.App })))

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {location.pathname === '/teleprompter' ? <TeleprompterPage /> : <Suspense fallback={<p>Loading deck…</p>}><App /></Suspense>}
  </StrictMode>,
)
