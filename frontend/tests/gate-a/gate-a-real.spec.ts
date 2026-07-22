import { expect, test } from "@playwright/test";

test("renders a Module 1 simulation after Module 2 and backend ingestion", async ({ page }) => {
  const statuses = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/rooms/status") && response.status() === 200,
  );
  const recommendations = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/recommendations") && response.status() === 200,
  );

  await page.goto("/");

  const statusPayload = await (await statuses).json();
  const recommendationPayload = await (await recommendations).json();
  const roomA = statusPayload.rooms.find((room: { room_id: string }) => room.room_id === "room_a");

  expect(roomA).toBeTruthy();
  expect(roomA.observed_at).not.toBeNull();
  expect(roomA.sensor_health.thermal).toBe("ok");
  expect(recommendationPayload.recommendations[0].room_id).toBe("room_a");
  await expect(page.getByRole("heading", { name: "Quiet Commons" })).toBeVisible();
  await expect(page.getByText("No RGB camera.")).toBeVisible();
});
