import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App, displayRoomStateLabel } from "../src/app/App";
import { mockRooms } from "../src/mocks/mockData";

describe("App", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          source: "nea",
          is_cached: false,
          station_name: "Clementi Road",
          location_label: "NUS · Clementi Road",
          observed_at: "2026-07-27T12:00:00+08:00",
          temperature_c: 29,
          apparent_temperature_c: 32,
          humidity_percent: 72,
          wind_kph: 8,
          weather_code: 2,
          condition: "Partly Cloudy",
        }),
      }),
    );
  });

  it("forces the displayed room state to Closed below relative light 0.2", () => {
    const darkRoom = {
      ...mockRooms[0],
      features: {
        ...mockRooms[0].features,
        light_relative_mean: 0.19,
      },
    };
    const thresholdRoom = {
      ...darkRoom,
      features: {
        ...darkRoom.features,
        light_relative_mean: 0.2,
      },
    };

    expect(displayRoomStateLabel(darkRoom, "en")).toBe("Closed");
    expect(displayRoomStateLabel(darkRoom, "zh")).toBe("Closed");
    expect(displayRoomStateLabel(thresholdRoom, "en")).toBe(
      "Recommended for quiet study",
    );
  });

  it("requires login and renders a simple personalized student home", async () => {
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByRole("heading", { name: "找到更适合你的学习空间" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "填入学生演示账户" }));
    await user.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByText("为你推荐")).toBeInTheDocument();
    expect(screen.getAllByText("非常适合你").length).toBeGreaterThan(0);
    expect(screen.getByText("只分析空间，不识别个人")).toBeInTheDocument();
    expect(screen.queryByText("声音 RMS")).not.toBeInTheDocument();
    expect(screen.queryByText("置信度")).not.toBeInTheDocument();
  });

  it("stores preferences and changes the personalized top room", async () => {
    const user = userEvent.setup();
    const { container } = render(<App />);
    await user.click(await screen.findByRole("button", { name: "填入学生演示账户" }));
    await user.click(screen.getByRole("button", { name: "登录" }));
    await screen.findByText("为你推荐");

    await user.click(screen.getAllByRole("button", { name: "偏好" })[0]);
    await user.click(screen.getByRole("button", { name: /小组讨论/ }));
    await user.click(screen.getByRole("button", { name: "保存偏好" }));
    expect(await screen.findByText("已保存，首页推荐已更新")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "首页" })[0]);

    expect(container.querySelector(".recommendation-card.featured h3")?.textContent).toBe("NUS-ISS Collaborative Classroom");
  });

  it("keeps classroom data behind an image-led detail view", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "填入学生演示账户" }));
    await user.click(screen.getByRole("button", { name: "登录" }));
    await user.click((await screen.findAllByRole("button", { name: "教室" }))[0]);

    expect(await screen.findByRole("heading", { name: "发现教室" })).toBeInTheDocument();
    expect(document.querySelectorAll(".room-card")).toHaveLength(9);
    const roomImages = Array.from(document.querySelectorAll<HTMLImageElement>(".room-card img"));
    expect(roomImages).toHaveLength(9);
    expect(roomImages.every((image) => !image.src.includes("nus-college-classroom"))).toBe(true);
    fireEvent.error(roomImages[1]);
    expect(roomImages[1].src).toContain("/rooms/nus-erc-alr.jpg");
    expect(screen.getByRole("button", { name: /ERC The Study/ })).toBeInTheDocument();
    expect(screen.queryByText("当前教室状态")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /ERC The Study/ }));
    expect(await screen.findByRole("heading", { name: "ERC The Study" })).toBeInTheDocument();
    expect(screen.getByText("8 College Avenue West, Singapore 138608")).toBeInTheDocument();
    expect(screen.getByText("与你的偏好匹配度")).toBeInTheDocument();
    expect(screen.getByText("24.0°C")).toBeInTheDocument();
    expect(screen.getByText("52%")).toBeInTheDocument();
  });

  it("routes administrator credentials to the quantitative console", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "管理员" }));
    await user.click(screen.getByRole("button", { name: "填入管理员演示账户" }));
    await user.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByRole("heading", { name: "运行总览" })).toBeInTheDocument();
    expect(screen.getByText("量化数据仅在管理员端展示")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "实时监测" }));
    expect(await screen.findByRole("heading", { name: "实时传感器监测" })).toBeInTheDocument();
    expect(await screen.findByText("当前实时人数")).toBeInTheDocument();
    expect(screen.getByTestId("live-people-count")).toHaveTextContent("--");
    expect(screen.getByText("实时隐私安全热成像")).toBeInTheDocument();
    expect(screen.getByText("无框 · 不识别身份")).toBeInTheDocument();
    expect(screen.queryByText(/个检测框/)).not.toBeInTheDocument();
    expect(screen.getByText("允许讨论")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "教室数据" }));
    expect(await screen.findByRole("heading", { name: "教室量化数据" })).toBeInTheDocument();
    expect(screen.getByText("声音 RMS")).toBeInTheDocument();
    expect(screen.getByText("置信度")).toBeInTheDocument();
  });

  it("switches the complete interface to professional English and remembers the choice", async () => {
    const user = userEvent.setup();
    const firstRender = render(<App />);

    await user.click(await screen.findByRole("button", { name: "切换为英文" }));
    expect(screen.getByRole("heading", { name: "Find a study space that works for you" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Administrator" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("en");

    await user.click(screen.getByRole("button", { name: "Use student demo account" }));
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Recommended for you")).toBeInTheDocument();
    expect(screen.getByText("Room-level analysis only; no identity recognition")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Rooms" })[0]);
    expect(await screen.findByRole("heading", { name: "Explore study rooms" })).toBeInTheDocument();

    firstRender.unmount();
    render(<App />);
    expect(await screen.findByRole("button", { name: "Switch to Chinese" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("en");
  });

  it("translates quantitative administrator monitoring into English", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "切换为英文" }));
    await user.click(screen.getByRole("button", { name: "Administrator" }));
    await user.click(screen.getByRole("button", { name: "Use administrator demo account" }));
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Operational overview" })).toBeInTheDocument();
    expect(screen.getByText("Quantitative data is restricted to administrators")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Live monitor" }));
    expect(await screen.findByRole("heading", { name: "Live sensor monitoring" })).toBeInTheDocument();
    expect(screen.getByText("Current live people count")).toBeInTheDocument();
    expect(screen.getByText("Live privacy-safe thermal view")).toBeInTheDocument();
    expect(screen.getByText("No boxes · no identity recognition")).toBeInTheDocument();
    expect(screen.getByText("Discussion allowed")).toBeInTheDocument();
  });

  it("uses today's goal in a dedicated AI advisor page without changing saved preferences", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "切换为英文" }));
    await user.click(screen.getByRole("button", { name: "Use student demo account" }));
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await user.click((await screen.findAllByRole("button", { name: "AI Advisor" }))[0]);

    expect(await screen.findByRole("heading", { name: "Match today's task to the right space" })).toBeInTheDocument();
    expect(screen.getByText("These are the current top three from your saved preferences.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Example 1" }));
    await user.click(screen.getByRole("button", { name: "Find the best room" }));

    expect(await screen.findByText("Best fit for today")).toBeInTheDocument();
    expect(screen.getByText("Group discussion")).toBeInTheDocument();
    expect(screen.getByText(/will not overwrite saved long-term preferences/i)).toBeInTheDocument();
  });
});
