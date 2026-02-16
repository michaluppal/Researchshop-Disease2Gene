/**
 * Multi-provider AI API service layer with a common interface.
 * All providers use native fetch() over HTTPS.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AIModel {
  id: string;
  name: string;
  contextWindow: number;
  pricing?: { input: number; output: number };
}

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatParams {
  model: string;
  messages: ChatMessage[];
  temperature?: number;
  maxTokens?: number;
}

export interface ChatResponse {
  content: string;
  model: string;
  usage?: { inputTokens: number; outputTokens: number };
}

export interface AIProvider {
  name: string;
  models: AIModel[];
  validateKey(apiKey: string): Promise<boolean>;
  chat(params: ChatParams, apiKey: string): Promise<ChatResponse>;
}

// ---------------------------------------------------------------------------
// Anthropic
// ---------------------------------------------------------------------------

const ANTHROPIC_MODELS: AIModel[] = [
  {
    id: "claude-sonnet-4-20250514",
    name: "Claude Sonnet 4",
    contextWindow: 200_000,
    pricing: { input: 3, output: 15 },
  },
  {
    id: "claude-haiku-4-20250414",
    name: "Claude Haiku 4",
    contextWindow: 200_000,
    pricing: { input: 0.25, output: 1.25 },
  },
];

export class AnthropicProvider implements AIProvider {
  readonly name = "Anthropic";
  readonly models = ANTHROPIC_MODELS;
  private readonly baseUrl = "https://api.anthropic.com/v1";

  async validateKey(apiKey: string): Promise<boolean> {
    try {
      const res = await fetch(`${this.baseUrl}/messages`, {
        method: "POST",
        headers: {
          "x-api-key": apiKey,
          "anthropic-version": "2023-06-01",
          "content-type": "application/json",
        },
        body: JSON.stringify({
          model: "claude-haiku-4-20250414",
          max_tokens: 1,
          messages: [{ role: "user", content: "hi" }],
        }),
      });
      // 200 or 400 (bad request but valid key) means the key is accepted
      return res.status !== 401 && res.status !== 403;
    } catch {
      return false;
    }
  }

  async chat(params: ChatParams, apiKey: string): Promise<ChatResponse> {
    const systemMessages = params.messages.filter((m) => m.role === "system");
    const nonSystemMessages = params.messages.filter((m) => m.role !== "system");

    const body: Record<string, unknown> = {
      model: params.model,
      max_tokens: params.maxTokens ?? 4096,
      messages: nonSystemMessages.map((m) => ({
        role: m.role,
        content: m.content,
      })),
    };

    if (systemMessages.length > 0) {
      body.system = systemMessages.map((m) => m.content).join("\n\n");
    }
    if (params.temperature !== undefined) {
      body.temperature = params.temperature;
    }

    const res = await fetch(`${this.baseUrl}/messages`, {
      method: "POST",
      headers: {
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Anthropic API error ${res.status}: ${text}`);
    }

    const data = (await res.json()) as {
      content: { type: string; text: string }[];
      model: string;
      usage: { input_tokens: number; output_tokens: number };
    };

    return {
      content: data.content
        .filter((c) => c.type === "text")
        .map((c) => c.text)
        .join(""),
      model: data.model,
      usage: {
        inputTokens: data.usage.input_tokens,
        outputTokens: data.usage.output_tokens,
      },
    };
  }
}

// ---------------------------------------------------------------------------
// DeepSeek
// ---------------------------------------------------------------------------

const DEEPSEEK_MODELS: AIModel[] = [
  {
    id: "deepseek-chat",
    name: "DeepSeek Chat",
    contextWindow: 128_000,
    pricing: { input: 0.14, output: 0.28 },
  },
  {
    id: "deepseek-reasoner",
    name: "DeepSeek Reasoner",
    contextWindow: 128_000,
    pricing: { input: 0.55, output: 2.19 },
  },
];

export class DeepSeekProvider implements AIProvider {
  readonly name = "DeepSeek";
  readonly models = DEEPSEEK_MODELS;
  private readonly baseUrl = "https://api.deepseek.com/v1";

  async validateKey(apiKey: string): Promise<boolean> {
    try {
      const res = await fetch(`${this.baseUrl}/chat/completions`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: "deepseek-chat",
          max_tokens: 1,
          messages: [{ role: "user", content: "hi" }],
        }),
      });
      return res.status !== 401 && res.status !== 403;
    } catch {
      return false;
    }
  }

  async chat(params: ChatParams, apiKey: string): Promise<ChatResponse> {
    const res = await fetch(`${this.baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: params.model,
        messages: params.messages.map((m) => ({
          role: m.role,
          content: m.content,
        })),
        temperature: params.temperature,
        max_tokens: params.maxTokens ?? 4096,
      }),
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`DeepSeek API error ${res.status}: ${text}`);
    }

    const data = (await res.json()) as OpenAICompletionResponse;
    return parseOpenAIResponse(data);
  }
}

// ---------------------------------------------------------------------------
// OpenRouter
// ---------------------------------------------------------------------------

const OPENROUTER_MODELS: AIModel[] = [
  {
    id: "anthropic/claude-sonnet-4-20250514",
    name: "Claude Sonnet 4 (OpenRouter)",
    contextWindow: 200_000,
  },
  {
    id: "google/gemini-2.5-flash-preview",
    name: "Gemini 2.5 Flash (OpenRouter)",
    contextWindow: 1_000_000,
  },
  {
    id: "deepseek/deepseek-chat",
    name: "DeepSeek Chat (OpenRouter)",
    contextWindow: 128_000,
  },
  {
    id: "meta-llama/llama-3.1-70b-instruct",
    name: "Llama 3.1 70B (OpenRouter)",
    contextWindow: 131_072,
  },
];

export class OpenRouterProvider implements AIProvider {
  readonly name = "OpenRouter";
  readonly models = OPENROUTER_MODELS;
  private readonly baseUrl = "https://openrouter.ai/api/v1";

  async validateKey(apiKey: string): Promise<boolean> {
    try {
      const res = await fetch(`${this.baseUrl}/auth/key`, {
        headers: { Authorization: `Bearer ${apiKey}` },
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  async chat(params: ChatParams, apiKey: string): Promise<ChatResponse> {
    const res = await fetch(`${this.baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://disease2gene.app",
        "X-Title": "Disease2Gene",
      },
      body: JSON.stringify({
        model: params.model,
        messages: params.messages.map((m) => ({
          role: m.role,
          content: m.content,
        })),
        temperature: params.temperature,
        max_tokens: params.maxTokens ?? 4096,
      }),
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`OpenRouter API error ${res.status}: ${text}`);
    }

    const data = (await res.json()) as OpenAICompletionResponse;
    return parseOpenAIResponse(data);
  }
}

// ---------------------------------------------------------------------------
// Together AI
// ---------------------------------------------------------------------------

const TOGETHER_MODELS: AIModel[] = [
  {
    id: "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
    name: "Llama 3.1 70B Instruct Turbo",
    contextWindow: 131_072,
    pricing: { input: 0.88, output: 0.88 },
  },
  {
    id: "mistralai/Mixtral-8x22B-Instruct-v0.1",
    name: "Mixtral 8x22B Instruct",
    contextWindow: 65_536,
    pricing: { input: 1.2, output: 1.2 },
  },
  {
    id: "Qwen/Qwen2.5-72B-Instruct-Turbo",
    name: "Qwen 2.5 72B Instruct Turbo",
    contextWindow: 131_072,
    pricing: { input: 1.2, output: 1.2 },
  },
];

export class TogetherAIProvider implements AIProvider {
  readonly name = "Together AI";
  readonly models = TOGETHER_MODELS;
  private readonly baseUrl = "https://api.together.xyz/v1";

  async validateKey(apiKey: string): Promise<boolean> {
    try {
      const res = await fetch(`${this.baseUrl}/models`, {
        headers: { Authorization: `Bearer ${apiKey}` },
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  async chat(params: ChatParams, apiKey: string): Promise<ChatResponse> {
    const res = await fetch(`${this.baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: params.model,
        messages: params.messages.map((m) => ({
          role: m.role,
          content: m.content,
        })),
        temperature: params.temperature,
        max_tokens: params.maxTokens ?? 4096,
      }),
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Together AI API error ${res.status}: ${text}`);
    }

    const data = (await res.json()) as OpenAICompletionResponse;
    return parseOpenAIResponse(data);
  }
}

// ---------------------------------------------------------------------------
// Gemini (backward compatibility with existing pipeline)
// ---------------------------------------------------------------------------

const GEMINI_MODELS: AIModel[] = [
  {
    id: "gemini-2.0-flash",
    name: "Gemini 2.0 Flash",
    contextWindow: 1_048_576,
    pricing: { input: 0.1, output: 0.4 },
  },
  {
    id: "gemini-2.5-flash-preview-05-20",
    name: "Gemini 2.5 Flash",
    contextWindow: 1_048_576,
    pricing: { input: 0.15, output: 0.6 },
  },
];

export class GeminiProvider implements AIProvider {
  readonly name = "Gemini";
  readonly models = GEMINI_MODELS;
  private readonly baseUrl =
    "https://generativelanguage.googleapis.com/v1beta/models";

  async validateKey(apiKey: string): Promise<boolean> {
    try {
      const res = await fetch(`${this.baseUrl}?key=${apiKey}`);
      return res.ok;
    } catch {
      return false;
    }
  }

  async chat(params: ChatParams, apiKey: string): Promise<ChatResponse> {
    const systemParts = params.messages
      .filter((m) => m.role === "system")
      .map((m) => m.content);

    const contents = params.messages
      .filter((m) => m.role !== "system")
      .map((m) => ({
        role: m.role === "assistant" ? "model" : "user",
        parts: [{ text: m.content }],
      }));

    const body: Record<string, unknown> = { contents };

    if (systemParts.length > 0) {
      body.systemInstruction = {
        parts: [{ text: systemParts.join("\n\n") }],
      };
    }

    body.generationConfig = {
      temperature: params.temperature,
      maxOutputTokens: params.maxTokens ?? 4096,
    };

    const url = `${this.baseUrl}/${params.model}:generateContent?key=${apiKey}`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Gemini API error ${res.status}: ${text}`);
    }

    const data = (await res.json()) as {
      candidates: {
        content: { parts: { text: string }[] };
      }[];
      usageMetadata?: {
        promptTokenCount: number;
        candidatesTokenCount: number;
      };
    };

    const textContent =
      data.candidates?.[0]?.content?.parts
        ?.map((p) => p.text)
        .join("") ?? "";

    return {
      content: textContent,
      model: params.model,
      usage: data.usageMetadata
        ? {
            inputTokens: data.usageMetadata.promptTokenCount,
            outputTokens: data.usageMetadata.candidatesTokenCount,
          }
        : undefined,
    };
  }
}

// ---------------------------------------------------------------------------
// Shared helpers (OpenAI-compatible response format)
// ---------------------------------------------------------------------------

interface OpenAICompletionResponse {
  choices: {
    message: { role: string; content: string };
    finish_reason: string;
  }[];
  model: string;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
  };
}

function parseOpenAIResponse(data: OpenAICompletionResponse): ChatResponse {
  const choice = data.choices[0];
  if (!choice) {
    throw new Error("No completion choice returned from API");
  }
  return {
    content: choice.message.content,
    model: data.model,
    usage: data.usage
      ? {
          inputTokens: data.usage.prompt_tokens,
          outputTokens: data.usage.completion_tokens,
        }
      : undefined,
  };
}

// ---------------------------------------------------------------------------
// Provider registry
// ---------------------------------------------------------------------------

const providers: Map<string, AIProvider> = new Map();

function ensureRegistered(): void {
  if (providers.size > 0) return;
  const instances: AIProvider[] = [
    new AnthropicProvider(),
    new DeepSeekProvider(),
    new OpenRouterProvider(),
    new TogetherAIProvider(),
    new GeminiProvider(),
  ];
  for (const p of instances) {
    providers.set(p.name, p);
  }
}

export function getProvider(name: string): AIProvider | undefined {
  ensureRegistered();
  return providers.get(name);
}

export function listProviders(): AIProvider[] {
  ensureRegistered();
  return [...providers.values()];
}

export function listAllModels(): { provider: string; model: AIModel }[] {
  ensureRegistered();
  const result: { provider: string; model: AIModel }[] = [];
  for (const p of providers.values()) {
    for (const m of p.models) {
      result.push({ provider: p.name, model: m });
    }
  }
  return result;
}
