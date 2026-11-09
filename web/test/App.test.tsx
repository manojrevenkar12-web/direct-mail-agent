import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import data from "../public/data/console.json";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const ok = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));

describe("approval console", () => {
  it("shows a skeleton, then the round with its checks", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => ok(data));
    render(<App />);
    expect(screen.getByLabelText("Loading the round")).toBeTruthy();
    await waitFor(() => expect(screen.getByText(`Round ${data.sample.round}`)).toBeTruthy());
    expect(screen.getByText("Nobody suppressed is mailed")).toBeTruthy();
    expect(screen.getByText("What mail was worth")).toBeTruthy();
  });

  it("explains an error and loads again on retry", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockImplementationOnce(() => Promise.resolve(new Response("", { status: 503 })));
    f.mockImplementation(() => ok(data));
    render(<App />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByText(/answered 503/)).toBeTruthy();
    await act(async () => fireEvent.click(screen.getByText("Load again")));
    await waitFor(() => expect(screen.getByText(`Round ${data.sample.round}`)).toBeTruthy());
  });

  it("says there is nothing to approve when the round is paused", async () => {
    const paused = { ...data, sample: { ...data.sample, plan: { ...data.sample.plan, paused: true, letters: 0 } } };
    vi.spyOn(globalThis, "fetch").mockImplementation(() => ok(paused));
    render(<App />);
    await waitFor(() => expect(screen.getByText(/is paused/)).toBeTruthy());
  });

  it("stamps the approval and names the exact file", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => ok(data));
    render(<App />);
    await waitFor(() => expect(screen.getByText("Approve for print")).toBeTruthy());
    await act(async () => fireEvent.click(screen.getByText("Approve for print")));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Approved for print"));
    expect(screen.getByText(new RegExp(`Released as file ${data.sample.sha256.slice(0, 12)}`))).toBeTruthy();
  });
});
