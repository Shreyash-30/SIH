import './App.css'
import Navbar from './components/Navbar.jsx'
import Home from './pages/Home.jsx'
import ProcessSteps from './components/ProcessSteps.jsx'
import FileUploadBox from './components/FileUploadBox.jsx'

function App() {
  return (
    <>
      <Navbar />
      <ProcessSteps />
      <FileUploadBox />
      {/* <Home /> */}
    </>
  )
}

export default App
