import { expect, test, type Page } from "@playwright/test";

async function mockWeather(page: Page) {
  await page.route("**/api/v1/weather", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
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
}

async function openStudentPage(page: Page, name: "首页" | "教室" | "偏好" | "账户" | "Home" | "Rooms" | "Preferences" | "Account") {
  const menu = page.getByRole("button", { name: /打开菜单|Open menu/ });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("button", { name, exact: true }).first().click();
}

test("student flow keeps the home simple and updates personalized ranking", async ({ page }) => {
  await mockWeather(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "找到更适合你的学习空间" })).toBeVisible();
  await page.getByRole("button", { name: "填入学生演示账户" }).click();
  await page.getByRole("button", { name: "登录", exact: true }).click();

  await expect(page.getByText("为你推荐")).toBeVisible();
  await expect(page.locator(".recommendation-card.featured h3")).toHaveText("ERC The Study");
  await expect(page.getByText("只分析空间，不识别个人")).toBeVisible();
  await expect(page.getByText("29°C · 多云")).toBeVisible();
  await expect(page.getByText("置信度")).toHaveCount(0);

  await openStudentPage(page, "偏好");
  await page.getByRole("button", { name: /小组讨论/ }).click();
  await page.getByRole("button", { name: "保存偏好" }).click();
  await expect(page.getByText("已保存，首页推荐已更新")).toBeVisible();
  await openStudentPage(page, "首页");
  await expect(page.locator(".recommendation-card.featured h3")).toHaveText("NUS-ISS Collaborative Classroom");

  await openStudentPage(page, "教室");
  await expect(page.getByRole("heading", { name: "发现教室" })).toBeVisible();
  await expect(page.locator(".room-card")).toHaveCount(9);
  await page.getByRole("button", { name: /ERC The Study/ }).click();
  await expect(page.getByRole("heading", { name: "ERC The Study" })).toBeVisible();
  await expect(page.getByText("8 College Avenue West, Singapore 138608")).toBeVisible();
  await expect(page.getByText("与你的偏好匹配度")).toBeVisible();
  await expect(page.getByText("实时量化遥测")).toHaveCount(0);
});

test("administrator login opens quantitative views", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "管理员" }).click();
  await page.getByRole("button", { name: "填入管理员演示账户" }).click();
  await page.getByRole("button", { name: "登录", exact: true }).click();

  await expect(page.getByRole("heading", { name: "运行总览" })).toBeVisible();
  await expect(page.getByText("量化数据仅在管理员端展示")).toBeVisible();
  await page.getByRole("button", { name: "实时监测" }).click();
  await expect(page.getByRole("heading", { name: "实时传感器监测" })).toBeVisible();
  await expect(page.getByText("模型预测人数")).toBeVisible();
  await expect(page.getByText("实时热成像与热区检测")).toBeVisible();
  await expect(page.locator(".thermal-canvas-wrap canvas")).toBeVisible();
  await expect(page.getByText("2 个检测框")).toBeVisible();
  await page.getByRole("button", { name: "教室数据" }).click();
  await expect(page.getByRole("heading", { name: "教室量化数据" })).toBeVisible();
  await expect(page.getByText("声音 RMS")).toBeVisible();
  await expect(page.getByText("置信度")).toBeVisible();

  await page.getByRole("button", { name: "切换为英文" }).click();
  await expect(page.getByRole("heading", { name: "Quantitative room data" })).toBeVisible();
  await page.getByRole("button", { name: "Live monitor" }).click();
  await expect(page.getByRole("heading", { name: "Live sensor monitoring" })).toBeVisible();
  await expect(page.getByText("Model-estimated occupancy")).toBeVisible();
  await expect(page.getByText("Discussion allowed")).toBeVisible();
});

test("language control switches and persists the English student experience", async ({ page }) => {
  await mockWeather(page);
  await page.goto("/");
  await page.getByRole("button", { name: "切换为英文" }).click();
  await expect(page.getByRole("heading", { name: "Find a study space that works for you" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Administrator" })).toBeVisible();

  await page.getByRole("button", { name: "Use student demo account" }).click();
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByText("Recommended for you")).toBeVisible();
  await openStudentPage(page, "Rooms");
  await expect(page.getByRole("heading", { name: "Explore study rooms" })).toBeVisible();
  await expect(page.getByText("Term time · 09:00–22:00")).toBeVisible();

  await page.reload();
  await expect(page.getByRole("button", { name: "Switch to Chinese" })).toBeVisible();
  await expect(page.getByText("Recommended for you")).toBeVisible();
});
