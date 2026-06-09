import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
});

// jsdom doesn't ship ResizeObserver but Recharts' ResponsiveContainer
// reaches for it on mount.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Stub navigator.mediaDevices for VoiceRecorder tests.
if (!("mediaDevices" in navigator)) {
  Object.defineProperty(navigator, "mediaDevices", {
    value: { getUserMedia: vi.fn().mockRejectedValue(new Error("not implemented")) },
    configurable: true,
  });
}
