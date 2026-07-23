import { Route, Routes } from "react-router-dom";

import { AdminPage } from "./pages/admin-page";
import { HomePage } from "./pages/home-page";
import { ImagesPage } from "./pages/images-page";
import { PreviewPage } from "./pages/preview-page";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/images" element={<ImagesPage />} />
      <Route path="/documents/:id" element={<PreviewPage />} />
      <Route path="/admin" element={<AdminPage />} />
    </Routes>
  );
}
