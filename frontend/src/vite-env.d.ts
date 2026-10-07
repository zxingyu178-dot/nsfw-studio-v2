/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 显式指定后端地址；缺省走同源（开发期由 Vite 代理 /api） */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
