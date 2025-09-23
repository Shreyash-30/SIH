import './home.css'
import FileUploadBox from '../components/FileUploadBox'

function Home() {
  return (
    <main className="home">
      <section className="home__hero">
        <h1 className="home__title">Groundwater Quality Assessment</h1>
        <p className="home__subtitle">Upload your lab report to see classification and indices.</p>
      </section>

      <section className="home__content" style={{ maxWidth: '1200px', margin: '0 auto' }}>
        <FileUploadBox />
      </section>
    </main>
  )
}

export default Home




