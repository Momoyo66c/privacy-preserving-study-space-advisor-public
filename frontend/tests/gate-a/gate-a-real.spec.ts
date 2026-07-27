import { expect, test } from "@playwright/test";

test("renders a Module 1 simulation after Module 2 and backend ingestion", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "还没有账户？创建用户" }).click();
  await page.getByLabel("用户名").fill("gate-a-user");
  await page.getByLabel("密码").fill("gate-a-password");

  const statuses = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/rooms/status") && response.status() === 200,
  );
  const recommendations = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/me/recommendations") && response.status() === 200,
  );
  await page.getByRole("button", { name: "创建并登录" }).click();

  const statusPayload = await (await statuses).json();
  const recommendationPayload = await (await recommendations).json();
  const roomA = statusPayload.rooms.find((room: { room_id: string }) => room.room_id === "room_a");

  expect(roomA).toBeTruthy();
  expect(roomA.observed_at).not.toBeNull();
  expect(roomA.sensor_health.thermal).toBe("ok");
  expect(recommendationPayload.recommendations[0].room_id).toBe("room_a");
  await expect(page.getByText("为你推荐")).toBeVisible();
  await expect(page.locator(".recommendation-card.featured h3")).toHaveText("ERC The Study");
  await expect(page.getByText("只分析空间，不识别个人")).toBeVisible();
});
