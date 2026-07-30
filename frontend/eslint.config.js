import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'


export default [
  {
    ignores: [
      '.vite/**',
      'dist/**',
      'coverage/**',
      'node_modules/**',
      'playwright-report/**',
      'test-results/**',
      '../static/vue/**'
    ]
  },
  js.configs.recommended,
  ...pluginVue.configs['flat/essential'],
  {
    files: ['**/*.{js,vue}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node
      }
    },
    rules: {
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      'vue/html-self-closing': 'off',
      'vue/multi-word-component-names': 'off'
    }
  }
]
