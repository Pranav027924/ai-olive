import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FileDropzone } from "./FileDropzone";

describe("FileDropzone", () => {
  it("invokes onFile with the dropped file", async () => {
    const onFile = vi.fn();
    render(<FileDropzone onFile={onFile} />);

    const dropzone = screen.getByTestId("file-dropzone");
    const file = new File(["hi"], "hi.pdf", { type: "application/pdf" });
    const dataTransfer = {
      files: [file],
      items: [{ kind: "file", type: file.type, getAsFile: () => file }],
      types: ["Files"],
    };
    await userEvent.pointer({ target: dropzone });
    // userEvent has no native drop; dispatch a real DragEvent
    dropzone.dispatchEvent(
      Object.assign(new Event("dragover", { bubbles: true }), { dataTransfer }) as Event,
    );
    dropzone.dispatchEvent(
      Object.assign(new Event("drop", { bubbles: true }), { dataTransfer, preventDefault() {} }),
    );

    expect(onFile).toHaveBeenCalledWith(file);
  });

  it("invokes onFile when a file is selected via the input", async () => {
    const onFile = vi.fn();
    const { container } = render(<FileDropzone onFile={onFile} />);

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["hi"], "hi.pdf", { type: "application/pdf" });
    await userEvent.upload(input, file);

    expect(onFile).toHaveBeenCalledWith(file);
  });
});
