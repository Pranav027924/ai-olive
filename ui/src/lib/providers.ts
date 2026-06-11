import type { Provider } from "@/api/types";

export interface ProviderOption {
  value: Provider;
  label: string;
  defaultModel: string;
}

export const PROVIDERS: ProviderOption[] = [
  { value: "anthropic", label: "Anthropic", defaultModel: "claude-opus-4-7" },
  { value: "openai", label: "OpenAI", defaultModel: "gpt-4o-mini" },
  { value: "gemini", label: "Gemini", defaultModel: "gemini-2.0-flash" },
  { value: "deepseek", label: "DeepSeek", defaultModel: "deepseek-chat" },
];

export function defaultModelFor(provider: Provider): string {
  return PROVIDERS.find((p) => p.value === provider)?.defaultModel ?? "claude-opus-4-7";
}
