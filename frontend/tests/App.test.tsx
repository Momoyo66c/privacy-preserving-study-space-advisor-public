import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../src/app/App";

describe("App", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("renders student-friendly recommendations with privacy guidance", async () => {
    render(<App />);
    expect((await screen.findAllByText("Quiet Commons")).length).toBeGreaterThan(0);
    expect(screen.getByText("No RGB camera.")).toBeInTheDocument();
    expect(screen.getByText("Best")).toBeInTheDocument();
    expect(screen.queryByText(/LLM_TEMPLATE_FALLBACK/)).not.toBeInTheDocument();
  });

  it("changes the top recommendation when switching to discussion mode", async () => {
    const user = userEvent.setup();
    render(<App />);
    expect((await screen.findAllByText("Quiet Commons")).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Discussion" }));
    await user.click(screen.getByRole("button", { name: "Apply preferences" }));
    expect(await screen.findByText(/Discussion Hub is ranked #1/)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Discussion Hub" })).toBeInTheDocument();
  });

  it("opens the admin operations dashboard", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Admin view" }));
    expect(await screen.findByRole("heading", { name: "Sign in to operations console" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Username"), "admin");
    await user.type(screen.getByLabelText("Password"), "admin123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Space health at a glance" })).toBeInTheDocument();
    expect(screen.getByText("Sensor matrix")).toBeInTheDocument();
    expect(screen.getByText("Privacy and data quality")).toBeInTheDocument();
  });
});
