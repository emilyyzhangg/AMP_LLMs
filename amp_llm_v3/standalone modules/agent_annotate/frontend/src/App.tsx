import { Routes, Route } from "react-router-dom";
import Header from "./components/Header";
import AuthGate from "./components/AuthGate";
import SubmitPage from "./components/SubmitPage";
import PipelinePage from "./components/PipelinePage";
import ReviewPage from "./components/ReviewPage";
import ResultsPage from "./components/ResultsPage";
import ConcordancePage from "./components/ConcordancePage";
import SettingsPage from "./components/SettingsPage";
import JobsPage from "./components/JobsPage";

export default function App() {
  return (
    <AuthGate>
      <Header />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<SubmitPage />} />
          <Route path="/pipeline/:jobId" element={<PipelinePage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/results" element={<ResultsPage />} />
          <Route path="/results/:jobId" element={<ResultsPage />} />
          <Route path="/concordance" element={<ConcordancePage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/jobs" element={<JobsPage />} />
        </Routes>
      </main>
    </AuthGate>
  );
}
