import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { Screen } from "./pages/Screen";
import "./index.css";

const view = new URLSearchParams(window.location.search).get("view");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {view === "screen" ? <Screen /> : <App />}
  </React.StrictMode>,
);
