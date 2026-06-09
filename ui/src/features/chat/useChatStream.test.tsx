import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as sse from "@/api/sse";
import { useChatStream } from "./useChatStream";

describe("useChatStream", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("starts streaming, accumulates chunks, and finishes completed", async () => {
    vi.spyOn(sse, "streamChat").mockImplementation(async (_id, handlers) => {
      handlers.onChunk?.("hello ");
      handlers.onChunk?.("world");
      handlers.onFinished?.({ state: "completed", content: "hello world", error: null });
    });

    const { result } = renderHook(() => useChatStream());

    await act(async () => {
      await result.current.start("sid");
    });

    expect(result.current.text).toBe("hello world");
    expect(result.current.status).toBe("completed");
  });

  it("surfaces errors as errored status", async () => {
    vi.spyOn(sse, "streamChat").mockImplementation(async (_id, handlers) => {
      handlers.onError?.(new Error("boom"));
    });

    const { result } = renderHook(() => useChatStream());

    await act(async () => {
      await result.current.start("sid");
    });

    await waitFor(() => expect(result.current.status).toBe("errored"));
    expect(result.current.error).toBe("boom");
  });

  it("abort flips status to cancelled when streaming", async () => {
    let resolveStream!: () => void;
    vi.spyOn(sse, "streamChat").mockImplementation(
      () =>
        new Promise<void>((res) => {
          resolveStream = res;
        }),
    );

    const { result } = renderHook(() => useChatStream());

    act(() => {
      void result.current.start("sid");
    });

    act(() => {
      result.current.abort();
    });

    expect(result.current.status).toBe("cancelled");

    act(() => {
      resolveStream();
    });
  });
});
