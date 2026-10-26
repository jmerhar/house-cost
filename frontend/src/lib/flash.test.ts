import { screen, waitFor } from "@testing-library/svelte";
import { afterEach, describe, expect, it } from "vitest";
import { appFor, fakeApi, renderPage } from "../testing";
import Flash from "./Flash.svelte";
import { reveal } from "./reveal";
import { navigate } from "./router.svelte";

afterEach(() => {
  navigate("/", { replace: true });
  document.body.innerHTML = "";
});

describe("Flash", () => {
  it("shows a message on the page it was left for, and drops it on the next", async () => {
    navigate("/bills/7", { replace: true });
    const app = appFor(fakeApi({}).api);
    app.say("The file could not be attached.", "/bills/7", true);
    renderPage(Flash, app);

    expect(screen.getByRole("status")).toHaveTextContent("The file could not be attached.");
    expect(screen.getByRole("status")).toHaveClass("problem");

    navigate("/bills");
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    expect(app.flash).toBeNull();
  });

  it("waits for the page it was left for", () => {
    navigate("/bills", { replace: true });
    const app = appFor(fakeApi({}).api);
    app.say("Bill saved.", "/bills/9");
    renderPage(Flash, app);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

describe("reveal", () => {
  it("brings a form into view and puts the cursor in its first field", async () => {
    document.body.innerHTML = '<form id="target"><select><option>a</option></select><input /></form>';
    const form = document.getElementById("target")!;
    let scrolled = false;
    form.scrollIntoView = () => {
      scrolled = true;
    };
    await reveal("#target");

    expect(scrolled).toBe(true);
    expect(document.activeElement).toBe(form.querySelector("select"));
  });

  it("does nothing when the form is not there", async () => {
    await expect(reveal("#missing")).resolves.toBeUndefined();
  });
});

