import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

const benignResizeObserverWarning = 'ResizeObserver loop completed with undelivered notifications'

window.addEventListener('error', (event) => {
  if (event.message?.includes(benignResizeObserverWarning)) {
    event.stopImmediatePropagation()
  }
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
