function ProcessSteps() {
  return (
    <section className="bg-gray-50">
      <div className="max-w-[1200px] mx-auto px-4 py-8 md:py-12">
        <h2 className="text-xl md:text-2xl font-bold mb-5 md:mb-6" style={{ color: '#004E92' }}>
          Automate water quality workflow
        </h2>
        <div className="flex items-stretch justify-between gap-4 md:gap-6">
          <Step
            color="#004E92"
            highlight="#00AEEF"
            title="Upload"
            subtitle="Upload lab results (CSV, Excel, PDF) securely"
            ariaLabel="Upload Data"
            icon={
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="currentColor"
                className="w-8 h-8 md:w-10 md:h-10"
                aria-hidden="true"
              >
                <path d="M12 3a1 1 0 0 1 1 1v7.586l2.293-2.293a1 1 0 1 1 1.414 1.414l-4 4a1 1 0 0 1-1.414 0l-4-4A1 1 0 0 1 8.707 9.293L11 11.586V4a1 1 0 0 1 1-1z" />
                <path d="M4 13a1 1 0 0 1 1 1v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3a1 1 0 1 1 2 0v3a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4v-3a1 1 0 0 1 1-1z" />
              </svg>
            }
          />
          <Arrow />
          <Step
            color="#004E92"
            highlight="#00AEEF"
            title="Process"
            subtitle="Automated extraction, normalization, and calculation"
            ariaLabel="Auto-Process"
            icon={
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="currentColor"
                className="w-8 h-8 md:w-10 md:h-10"
                aria-hidden="true"
              >
                <path d="M11 2a1 1 0 0 1 2 0v1.06a8.004 8.004 0 0 1 3.48 1.442l.75-.75a1 1 0 1 1 1.414 1.415l-.75.75A8.004 8.004 0 0 1 19.94 11H21a1 1 0 1 1 0 2h-1.06a8.004 8.004 0 0 1-1.442 3.48l.75.75a1 1 0 0 1-1.415 1.414l-.75-.75A8.004 8.004 0 0 1 13 20.94V22a1 1 0 1 1-2 0v-1.06a8.004 8.004 0 0 1-3.48-1.442l-.75.75a1 1 0 0 1-1.414-1.415l.75-.75A8.004 8.004 0 0 1 3.06 13H2a1 1 0 1 1 0-2h1.06a8.004 8.004 0 0 1 1.442-3.48l-.75-.75A1 1 0 0 1 5.167 3.78l.75.75A8.004 8.004 0 0 1 11 3.06V2zM12 7a5 5 0 1 0 .001 10.001A5 5 0 0 0 12 7z" />
              </svg>
            }
          />
          <Arrow />
          <Step
            color="#004E92"
            highlight="#00AEEF"
            title="Analyze"
            subtitle="In-depth statistical & health risk assessment"
            ariaLabel="Analyze Data"
            icon={
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="currentColor"
                className="w-8 h-8 md:w-10 md:h-10"
                aria-hidden="true"
              >
                <path d="M4 3a1 1 0 0 0-1 1v14a3 3 0 0 0 3 3h13a1 1 0 1 0 0-2H6a1 1 0 0 1-1-1V4a1 1 0 0 0-1-1z" />
                <path d="M8 13a1 1 0 0 1 1-1h1v4H9a1 1 0 0 1-1-1v-2zm4-5a1 1 0 0 1 1-1h1v10h-1a1 1 0 0 1-1-1V8zm4 3a1 1 0 0 1 1-1h1v7h-1a1 1 0 0 1-1-1v-5z" />
              </svg>
            }
          />
          <Arrow />
          <Step
            color="#004E92"
            highlight="#00AEEF"
            title="Report"
            subtitle="Interactive dashboards, GIS maps & downloadable reports"
            ariaLabel="Visualize and Report"
            icon={
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="currentColor"
                className="w-8 h-8 md:w-10 md:h-10"
                aria-hidden="true"
              >
                <path d="M4 4a2 2 0 0 1 2-2h8.586a2 2 0 0 1 1.414.586l3.414 3.414A2 2 0 0 1 20 7.414V20a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4zm12 0H6v16h12V7.414L16 4z" />
                <path d="M8 10h8a1 1 0 1 1 0 2H8a1 1 0 1 1 0-2zm0 4h6a1 1 0 1 1 0 2H8a1 1 0 1 1 0-2z" />
              </svg>
            }
          />
        </div>
      </div>
    </section>
  )
}

function Step({ icon, title, subtitle, ariaLabel, color, highlight }) {
  return (
    <div
      className="flex-1 min-w-[160px] bg-white rounded-lg shadow-sm border border-gray-200 px-5 py-5 md:px-6 md:py-6 flex items-center gap-4 md:gap-5"
      style={{ borderTopColor: highlight, borderTopWidth: 6 }}
      role="group"
      aria-label={ariaLabel}
    >
      <div
        className="rounded-md p-2 text-white"
        style={{ backgroundColor: color }}
        aria-hidden="true"
      >
        {icon}
      </div>
      <div className="flex flex-col">
        <span className="text-base md:text-lg font-semibold" style={{ color }}>{title}</span>
        {subtitle && (
          <span className="text-xs md:text-sm text-gray-700 leading-snug">
            {subtitle}
          </span>
        )}
        <span className="sr-only">{ariaLabel}</span>
      </div>
    </div>
  )
}

function Arrow() {
  return (
    <div className="hidden sm:flex items-center" aria-hidden="true">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="#004E92"
        className="w-7 h-7 md:w-8 md:h-8"
      >
        <path d="M13.293 4.293a1 1 0 0 1 1.414 0l6 6a1 1 0 0 1 0 1.414l-6 6a1 1 0 0 1-1.414-1.414L17.586 13H3a1 1 0 1 1 0-2h14.586l-4.293-4.293a1 1 0 0 1 0-1.414z" />
      </svg>
    </div>
  )
}

export default ProcessSteps
