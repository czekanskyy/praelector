// SPDX-License-Identifier: Apache-2.0

export interface ProviderPreset {
  id: string;
  name: string;
  kind: string;
  preset: string;
  baseUrl: string;
  defaultModel: string;
  isCloud: boolean;
  supportsJsonSchema: boolean;
  helpText?: string;
}

export const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    id: "ollama",
    name: "Ollama",
    kind: "ollama",
    preset: "ollama",
    baseUrl: "http://127.0.0.1:11434/v1",
    defaultModel: "qwen2.5:14b-instruct",
    isCloud: false,
    supportsJsonSchema: true,
    helpText: "Local open-weight runner. Free and private. Runs offline.",
  },
  {
    id: "lm_studio",
    name: "LM Studio",
    kind: "lm_studio",
    preset: "lm_studio",
    baseUrl: "http://127.0.0.1:1234/v1",
    defaultModel: "qwen2.5-14b-instruct",
    isCloud: false,
    supportsJsonSchema: true,
    helpText: "Local runner with OpenAI-compatible endpoint. Runs offline.",
  },
  {
    id: "groq",
    name: "Groq",
    kind: "groq",
    preset: "groq",
    baseUrl: "https://api.groq.com/openai/v1",
    defaultModel: "llama-3.3-70b-versatile",
    isCloud: true,
    supportsJsonSchema: true,
    helpText: "Ultra-fast cloud inference with a generous free tier.",
  },
  {
    id: "openrouter",
    name: "OpenRouter",
    kind: "openrouter",
    preset: "openrouter",
    baseUrl: "https://openrouter.ai/api/v1",
    defaultModel: "meta-llama/llama-3.3-70b-instruct:free",
    isCloud: true,
    supportsJsonSchema: true,
    helpText: "Unified API with access to free (:free) and paid models.",
  },
  {
    id: "gemini",
    name: "Google Gemini",
    kind: "gemini",
    preset: "gemini",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta",
    defaultModel: "gemini-1.5-flash",
    isCloud: true,
    supportsJsonSchema: true,
    helpText: "Google AI Studio API with a generous free tier.",
  },
  {
    id: "openai",
    name: "OpenAI",
    kind: "openai",
    preset: "openai",
    baseUrl: "https://api.openai.com/v1",
    defaultModel: "gpt-4o-mini",
    isCloud: true,
    supportsJsonSchema: true,
    helpText: "Standard OpenAI developer platform (pay-per-token API).",
  },
  {
    id: "anthropic",
    name: "Anthropic",
    kind: "anthropic",
    preset: "anthropic",
    baseUrl: "https://api.anthropic.com/v1",
    defaultModel: "claude-3-5-haiku-latest",
    isCloud: true,
    supportsJsonSchema: true,
    helpText: "Anthropic Claude messages API (pay-per-token API).",
  },
  {
    id: "xai",
    name: "xAI",
    kind: "xai",
    preset: "xai",
    baseUrl: "https://api.x.ai/v1",
    defaultModel: "grok-2-mini",
    isCloud: true,
    supportsJsonSchema: true,
    helpText: "xAI Grok API with OpenAI-compatible schema support.",
  },
];
