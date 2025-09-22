import akamLogo from '../assets/akam_logo.png'
import cgwbLogo from '../assets/cgwb-updated-logo.png'
import g20Logo0 from '../assets/g-20-logo_0.png'
// removed duplicate G20 logo import

function Navbar() {
  return (
    <header className="bg-white border-b border-gray-200">
      <div className="max-w-[1200px] mx-auto px-4 py-3 flex items-center justify-between">
        <div className="shrink-0">
          <img src={cgwbLogo} alt="CGWB" className="h-14 md:h-16 w-auto" />
        </div>
        <div className="flex items-center gap-3 md:gap-5">
          <img src={akamLogo} alt="AKAM" className="h-12 md:h-14 w-auto" />
          <img src={g20Logo0} alt="G20" className="h-8 md:h-10 w-auto" />
        </div>
      </div>
    </header>
  )
}

export default Navbar


