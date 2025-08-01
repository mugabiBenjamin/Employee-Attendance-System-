import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Provider } from 'react-redux'
import './index.css'
import App from './App.tsx'
import store from './store'
import { setAuth } from './store/slices/authSlice'
import { authApi } from './api/auth'

// Restore auth state on app startup
const initializeAuth = async () => {
  const accessToken = localStorage.getItem('access_token')
  const refreshToken = localStorage.getItem('refresh_token')
  
  if (accessToken && refreshToken) {
    try {
      // Verify token is still valid by getting current user
      const user = await authApi.getCurrentUser()
      
      // Restore auth state
      store.dispatch(setAuth({
        access_token: accessToken,
        refresh_token: refreshToken,
        token_type: 'bearer',
        user
      }))
    } catch {
      // Token is invalid, clear stored tokens
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
    }
  }
}

// Initialize auth before rendering
initializeAuth().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <Provider store={store}>
        <App />
      </Provider>
    </StrictMode>,
  )
})