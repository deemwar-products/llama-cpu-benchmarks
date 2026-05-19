import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'llama-local-benchmarks',
  description:
    'Small-model tool-calling benchmarks on commodity CPU hardware — Qwen × Gemma × Phi at Q4_K_M, with and without TurboQuant KV-cache compression.',
  base: '/llama-local-benchmarks/',
  cleanUrls: true,
  lastUpdated: true,
  ignoreDeadLinks: [/^\/api\/cells\//],
  themeConfig: {
    nav: [
      { text: 'Article', link: '/article' },
      { text: 'Results', link: '/results' },
      { text: 'Spec', link: '/specs/llama-cpp-turboquant-benchmark' },
      { text: 'API', link: '/api' },
      {
        text: 'GitHub',
        link: 'https://github.com/deemwar-products/llama-local-benchmarks',
      },
    ],
    sidebar: [
      {
        text: 'Overview',
        items: [
          { text: 'Home', link: '/' },
          { text: 'Findings article', link: '/article' },
          { text: 'Results table', link: '/results' },
        ],
      },
      {
        text: 'Reference',
        items: [
          { text: 'Spec v1', link: '/specs/llama-cpp-turboquant-benchmark' },
          { text: 'Hardware target', link: '/hardware' },
          { text: 'HTTP API', link: '/api' },
        ],
      },
    ],
    outline: { level: [2, 3] },
    search: { provider: 'local' },
    socialLinks: [
      {
        icon: 'github',
        link: 'https://github.com/deemwar-products/llama-local-benchmarks',
      },
    ],
    footer: {
      message: 'Benchmarks run on deemwar prod-app-1 · Xeon E-2176G · CPU-only',
      copyright: '© 2026 deemwar-products',
    },
  },
})
