import { expect, test } from "@playwright/test";

test("dashboard demonstrates ranking changes and fallback states", async ({ page }) => {
  await page.goto("/?mode=mock");
  await expect(page.getByRole("heading", { name: "Quiet Commons" })).toBeVisible();
  await expect(page.getByText("Best")).toBeVisible();
  await page.getByRole("button", { name: "Discussion", exact: true }).click();
  await page.getByRole("button", { name: "Apply preferences" }).click();
  await expect(page.getByText(/Discussion Hub is ranked #1/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Discussion Hub" })).toBeVisible();
  await page.getByRole("button", { name: /Atrium Tables/ }).click();
  await expect(page.getByText(/Live signals for this room may be delayed/)).toBeVisible();
});

test("opens the dedicated privacy-safe thermal monitor", async ({ page }) => {
  await page.goto("/?mode=mock");
  await page.getByRole("link", { name: "Open full thermal monitor" }).click();
  await expect(page).toHaveURL(/\/thermal\?room=room_a&mode=mock/);
  await expect(page.getByRole("heading", { name: "Live thermal monitor" })).toBeVisible();
  await expect(page.getByRole("img", { name: /normalized non-camera thermal distribution/ })).toBeVisible();
  await expect(page.getByText(/does not create additional sensor detail/)).toBeVisible();
});
