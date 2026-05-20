import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'I tried 4 LLM speedup techniques on CPU. Three made it slower.',
  description:
    "A week of benchmarks on a Xeon CPU box. TurboQuant ≠ 8× faster, speculative decoding ≠ universal win, ik_llama.cpp breaks parallel calls. Gemma-4-E4B-it on stock llama.cpp wins. Eleven cells, full source, MIT.",
  base: '/llama-local-benchmarks/',
  cleanUrls: true,
  lastUpdated: true,
  ignoreDeadLinks: [/^\/api\/cells\//],
  themeConfig: {
    nav: [
      { text: 'Article', link: '/article' },
      { text: 'Engine bake-off', link: '/article-engines' },
      { text: 'Results', link: '/results' },
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
          { text: 'TBQ findings article', link: '/article' },
          { text: 'Engine bake-off (in progress)', link: '/article-engines' },
          { text: 'Results table', link: '/results' },
        ],
      },
      {
        text: 'Reference',
        items: [
          { text: 'Spec: TurboQuant bake-off', link: '/specs/llama-cpp-turboquant-benchmark' },
          { text: 'Spec: Engine bake-off (next)', link: '/specs/cpu-fast-inference-bake-off' },
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
      message: 'Benchmarks run on a single shared CPU host · Xeon E-2176G · CPU-only',
      copyright: '© 2026 deemwar-products',
    },
  },
})
