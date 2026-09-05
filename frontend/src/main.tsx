import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import './index.css'
import App from './App'
import Projects from './pages/Projects'
import ProjectDetail from './pages/ProjectDetail'
import Elements from './pages/Elements'
import Quantities from './pages/Quantities'
import Prices from './pages/Prices'
import Cost from './pages/Cost'
import Standard from './pages/Standard'

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Projects /> },
      { path: 'standard', element: <Standard /> },
      { path: 'projects/:id', element: <ProjectDetail /> },
      { path: 'projects/:id/drawings/:did', element: <Elements /> },
      { path: 'projects/:id/quantities', element: <Quantities /> },
      { path: 'projects/:id/prices', element: <Prices /> },
      { path: 'projects/:id/cost', element: <Cost /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
