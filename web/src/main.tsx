import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './i18n'
import './styles.css'
import './styles-i18n.css'

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
