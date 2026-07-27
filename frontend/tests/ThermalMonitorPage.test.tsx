import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ThermalMonitorPage } from "../src/app/ThermalMonitorPage";

describe("ThermalMonitorPage", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/thermal?room=room_a&mode=mock");
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  });

  it("renders the privacy-safe full thermal workspace", async () => {
    render(<ThermalMonitorPage />);

    expect(await screen.findByRole("heading", { name: "Live thermal monitor" })).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: /normalized non-camera thermal distribution/ })).toBeInTheDocument();
    expect(screen.getByText("Relative peak")).toBeInTheDocument();
    expect(screen.getByText(/does not create additional sensor detail/)).toBeInTheDocument();
    expect(screen.getByText(/No RGB image/)).toBeInTheDocument();
  });

  it("switches between smooth and sensor-pixel modes", async () => {
    const user = userEvent.setup();
    render(<ThermalMonitorPage />);
    await screen.findByRole("img", { name: /normalized non-camera thermal distribution/ });

    const pixelButton = screen.getByRole("button", { name: "Sensor pixels" });
    await user.click(pixelButton);
    expect(pixelButton).toHaveClass("active");
    expect(screen.getByRole("button", { name: "Smooth" })).not.toHaveClass("active");
  });
});
