import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { boundedCanvasSize, ThermalMonitorPage } from "../src/app/ThermalMonitorPage";

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

  it("bounds the backing canvas even when layout dimensions regress", () => {
    expect(boundedCanvasSize(16_777_217, 16_777_217, 2)).toEqual({
      width: 4096,
      height: 4096,
    });
    expect(boundedCanvasSize(Number.NaN, -10, Number.POSITIVE_INFINITY)).toEqual({
      width: 1,
      height: 1,
    });
  });
});
