import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles/index.css";

// Auto-detect base path: "/agent-annotate" when served via Cloudflare,
// "/" when accessed directly at localhost:9005
const path = window.location.pathname;
const basename = path.startsWith("/agent-annotate") ? "/agent-annotate" : "/";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter basename={basename}>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
