import './App.css'
import Navbar from './components/Navbar.jsx'
import ProcessSteps from './components/ProcessSteps.jsx'
import FileUploadBox from './components/FileUploadBox.jsx'
import ResultsPanel from './components/ResultsPanel.jsx'
import { Routes, Route } from 'react-router-dom'

function App() {
  return (
    <>
      <Navbar />
      <Routes>
        <Route
          path="/"
          element={(
            <>
              <ProcessSteps />
              <FileUploadBox />
            </>
          )}
        />
        <Route path="/results" element={<ResultsPanel />} />
      </Routes>
    </>
  )
}

export default App
