import { Route, Routes } from "react-router-dom";

import { HomePage } from "./pages/home-page";
import { PreviewPage } from "./pages/preview-page";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/documents/:id" element={<PreviewPage />} />
    </Routes>
  );
}
