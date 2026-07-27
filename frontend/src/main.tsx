import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { ThermalMonitorPage } from "./app/ThermalMonitorPage";
import "./styles/app.css?playful-v1";

const Page = window.location.pathname === "/thermal" ? ThermalMonitorPage : App;

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <Page />
  </StrictMode>,
);
