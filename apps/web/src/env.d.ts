/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
}

// biome-ignore lint/correctness/noUnusedVariables: ambient Vite type declaration
interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare global {
  namespace NodeJS {
    interface ProcessEnv {
      readonly API_URL?: string;
      readonly VITE_API_URL?: string;
      readonly HOST?: string;
      readonly PORT?: string;
      readonly NODE_ENV?: "development" | "production" | "test";
    }
  }
}

export {};
