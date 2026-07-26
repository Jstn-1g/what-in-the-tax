/// <reference types="vite/client" />
/// <reference types="vitest/config" />

interface ImportMetaEnv {
  readonly VITE_SUPPORT_ONCE_URL?: string
  readonly VITE_SUPPORT_MONTHLY_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
