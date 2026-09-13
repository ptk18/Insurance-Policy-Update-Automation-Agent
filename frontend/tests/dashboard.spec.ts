import { test, expect, type Page } from "@playwright/test";
import { resolve } from "node:path";
import { mkdir } from "node:fs/promises";
import AxeBuilder from "@axe-core/playwright";

const detail = (page: Page) =>
  page.getByRole("region", { name: "Selected request" });
const origin = { Origin: "http://127.0.0.1:3001" };
async function openWorkspace(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Open demo workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "No requests yet" }),
  ).toBeVisible();
}
async function create(page: Page, sample = "0", broker?: string) {
  await page.getByRole("button", { name: "New request", exact: true }).click();
  await page.getByLabel("Try a sample").selectOption(sample);
  if (broker) await page.getByLabel("Simulated broker").selectOption(broker);
  await page.getByRole("button", { name: "Submit request" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(
    detail(page)
      .getByText(/Ready for review|Needs information|Access blocked/, {
        exact: true,
      })
      .first(),
  ).toBeVisible();
}
async function capture(page: Page, name: string) {
  const audit = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    audit.violations.map((v) => ({
      id: v.id,
      nodes: v.nodes.map((node) => ({
        target: node.target,
        issue: node.failureSummary,
      })),
    })),
    `Accessibility: ${name}`,
  ).toEqual([]);
  if (process.env.CAPTURE_BASELINE !== "1") return;
  if (test.info().project.name !== "chromium") return;
  const directory = resolve("../_docs/screenshots");
  await mkdir(directory, { recursive: true });
  await page.screenshot({ path: `${directory}/${name}.png`, fullPage: true });
}

test("contact request is reviewed, explicitly approved, applied, and retained after reload", async ({
  page,
}) => {
  await page.goto("/");
  await capture(page, "welcome-wide");
  await openWorkspace(page);
  await capture(page, "empty-wide");
  await create(page);
  await expect(
    detail(page).getByRole("table", { name: "Policy changes" }),
  ).toContainText("sam.updated@example.com");
  await expect(
    detail(page).getByRole("button", { name: "Apply approved update" }),
  ).toHaveCount(0);
  await capture(page, "ready-wide");
  await page.getByRole("button", { name: "Approve v1" }).click();
  await expect(
    detail(page).getByText("Approved · update pending", { exact: true }),
  ).toBeVisible();
  await capture(page, "approved-wide");
  await page.getByRole("button", { name: "Apply approved update" }).click();
  await expect(
    detail(page).getByText("Completed", { exact: true }),
  ).toBeVisible();
  await expect(detail(page).getByText("Confirmation draft")).toBeVisible();
  await capture(page, "completed-wide");
  await page.getByRole("tab", { name: "Activity" }).click();
  await expect(
    detail(page).getByText("update applied", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: /DEMO-1001 Request/ }).click();
  await expect(
    detail(page).getByText("Completed", { exact: true }),
  ).toBeVisible();
});

test("slow intake prevents duplicate submission and retains a single saved request", async ({
  page,
}) => {
  await openWorkspace(page);
  await page.getByRole("button", { name: "New request", exact: true }).click();
  await page.getByLabel("Try a sample").selectOption("0");
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/backend/cases", async (route) => {
    if (route.request().method() === "POST") await gate;
    await route.continue();
  });
  try {
    await page.getByRole("button", { name: "Submit request" }).click();
    await expect(
      page.getByRole("button", { name: "Saving request…" }),
    ).toBeDisabled();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeVisible();
    const closeButton = page.getByRole("button", { name: "Close dialog" });
    await expect(closeButton).toBeDisabled();
    await closeButton.focus();
    await expect(closeButton).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog")).toBeVisible();
    await capture(page, "saving-request");
  } finally {
    release();
  }
  await expect(page.getByRole("button", { name: "Approve v1" })).toBeVisible();
  const rows = await (await page.request.get("/api/backend/cases")).json();
  expect(rows).toHaveLength(1);
});

test("an expired guest can open a new workspace without stale case selection", async ({
  page,
}) => {
  await openWorkspace(page);
  await create(page);
  await page.context().addCookies([
    {
      name: "policy_workspace",
      value: "invalid-synthetic-test-token",
      url: "http://127.0.0.1:3001",
      httpOnly: true,
      sameSite: "Strict",
    },
  ]);
  await page.getByRole("button", { name: "Refresh cases" }).click();
  await expect(
    page.getByRole("button", { name: "Open demo workspace" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open demo workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "No requests yet" }),
  ).toBeVisible();
  await create(page);
  await expect(page.getByRole("button", { name: "Approve v1" })).toBeVisible();
});

for (const [sample, label] of [
  ["2", "missing"],
  ["3", "conflicting"],
]) {
  test(`${label} evidence blocks the entire request; a corrected PDF creates a fresh review`, async ({
    page,
  }) => {
    await openWorkspace(page);
    await create(page, sample);
    await expect(
      detail(page).getByRole("button", { name: /^Approve/ }),
    ).toHaveCount(0);
    await capture(page, `${label}-wide`);
    await page
      .getByRole("button", { name: "Add information", exact: true })
      .click();
    await page
      .getByLabel("Reply or clarification")
      .fill("The corrected proof of address is attached.");
    await page
      .getByLabel("Upload corrected PDF")
      .setInputFiles(resolve("../src/policy_update/assets/proof-matching.pdf"));
    await page.getByRole("button", { name: "Save & check again" }).click();
    await expect(
      page.getByRole("button", { name: "Approve v2" }),
    ).toBeVisible();
    await expect(
      detail(page).getByText("Document text checked · Page 2"),
    ).toBeVisible();
    await capture(page, "corrected-wide");
    await page.getByRole("tab", { name: "Request & evidence" }).click();
    const download = page.waitForEvent("download");
    await page
      .getByRole("link", { name: "Download proof-matching.pdf" })
      .click();
    expect((await download).suggestedFilename()).toBe("proof-matching.pdf");
  });
}

test("editing an approved proposal invalidates approval; stale dialog submissions are refused", async ({
  page,
}) => {
  await openWorkspace(page);
  await create(page);
  await page.getByRole("button", { name: "Approve v1" }).click();
  await page.getByRole("button", { name: "Edit changes" }).click();
  await page
    .getByLabel("Email address", { exact: true })
    .fill("reviewed@example.com");
  await page.getByRole("button", { name: "Save new version" }).click();
  await expect(page.getByRole("button", { name: "Approve v2" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Apply approved update" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Edit changes" }).click();
  const rows = await (await page.request.get("/api/backend/cases")).json();
  const result = await page.request.put(
    `/api/backend/cases/${rows[0].id}/proposal`,
    {
      headers: origin,
      data: { expected_version: 2, changes: { phone: "+1 202 555 0155" } },
    },
  );
  expect(result.status()).toBe(200);
  await page.getByRole("button", { name: "Save new version" }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "Close this dialog, refresh the case",
  );
  await expect(page.getByLabel("Email address", { exact: true })).toHaveValue(
    "reviewed@example.com",
  );
  await capture(page, "stale-version-wide");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("button", { name: "Refresh cases" }).click();
  await expect(page.getByRole("button", { name: "Approve v3" })).toBeEnabled();
});

test("rejection records a reason and is terminal", async ({ page }) => {
  await openWorkspace(page);
  await create(page);
  await page.getByRole("button", { name: "Reject", exact: true }).click();
  await page
    .getByLabel("Reason for rejection")
    .fill("The broker withdrew this request.");
  await page
    .getByRole("button", { name: "Reject request", exact: true })
    .click();
  await expect(
    detail(page).getByText("Rejected", { exact: true }),
  ).toBeVisible();
  await expect(detail(page)).toContainText("The broker withdrew this request.");
  await expect(page.getByRole("button", { name: /^Approve/ })).toHaveCount(0);
  await capture(page, "rejected-wide");
});

test("guest cookies are private, workspaces are isolated, and cross-origin writes are rejected", async ({
  page,
  browser,
}) => {
  await openWorkspace(page);
  await create(page);
  const rows = await (await page.request.get("/api/backend/cases")).json();
  const cookie = (await page.context().cookies()).find(
    (c) => c.name === "policy_workspace",
  );
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe("Strict");
  expect(await page.evaluate(() => document.cookie)).not.toContain(
    "policy_workspace",
  );
  const other = await browser.newContext({ baseURL: "http://127.0.0.1:3001" });
  const second = await other.newPage();
  await openWorkspace(second);
  expect(
    (await second.request.get(`/api/backend/cases/${rows[0].id}`)).status(),
  ).toBe(404);
  const forbidden = await second.request.post("/api/backend/cases", {
    headers: { Origin: "https://untrusted.example" },
    data: {},
  });
  expect(forbidden.status()).toBe(403);
  expect(
    (await (await second.request.get("/api/backend/cases")).json()).length,
  ).toBe(0);
  await other.close();
});

test("unassigned broker is blocked without revealing policy contact values", async ({
  page,
}) => {
  await openWorkspace(page);
  await create(page, "0", "broker-jordan");
  await expect(
    detail(page).getByText("Access blocked", { exact: true }),
  ).toBeVisible();
  await expect(detail(page)).not.toContainText("sam@example.com");
  await expect(page.getByRole("button", { name: /^Approve/ })).toHaveCount(0);
  await capture(page, "blocked-wide");
});

test("keyboard tabs, dialog focus, narrow layout and error feedback remain usable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openWorkspace(page);
  await create(page);
  const reviewTab = page.getByRole("tab", { name: "Review", exact: true });
  await reviewTab.focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Request & evidence" }),
  ).toBeFocused();
  await page.keyboard.press("Home");
  await expect(reviewTab).toBeFocused();
  await page.getByRole("button", { name: "Edit changes" }).click();
  await expect(
    page.getByRole("button", { name: "Close dialog" }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Edit changes" }),
  ).toBeFocused();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await capture(page, "ready-mobile");
  await page.route("**/api/backend/cases/*/approve", (route) =>
    route.fulfill({
      status: 503,
      json: { detail: "Review service is temporarily unavailable." },
    }),
  );
  await page.getByRole("button", { name: "Approve v1" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "temporarily unavailable",
  );
  await expect(
    page.getByRole("button", { name: "Apply approved update" }),
  ).toHaveCount(0);
});

test("a persisted extraction failure exposes the safe error and retries to review", async ({
  page,
}) => {
  await openWorkspace(page);
  await page.getByRole("button", { name: "New request", exact: true }).click();
  await page
    .getByLabel("Paste email", { exact: true })
    .fill("RETRY-SCENARIO: DEMO-1001 email to retry@example.com");
  await page.getByRole("button", { name: "Submit request" }).click();
  await expect(detail(page).getByRole("alert")).toContainText(
    "429 RESOURCE_EXHAUSTED",
  );
  await expect(
    detail(page).getByRole("button", { name: /^Approve/ }),
  ).toHaveCount(0);
  await capture(page, "failed-wide");
  await page.getByRole("button", { name: "Retry processing" }).click();
  await expect(page.getByRole("button", { name: "Approve v1" })).toBeVisible();
  await expect(detail(page).getByRole("table")).toContainText(
    "retry@example.com",
  );
  const rows = await (await page.request.get("/api/backend/cases")).json();
  const record = await (
    await page.request.get(`/api/backend/cases/${rows[0].id}`)
  ).json();
  expect(record.job.attempts).toBe(2);
});
