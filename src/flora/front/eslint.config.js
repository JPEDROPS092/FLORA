// @ts-check
const eslint = require('@eslint/js');
const {defineConfig} = require('eslint/config');
const tseslint = require('typescript-eslint');
const angular = require('angular-eslint');

module.exports = defineConfig([
  {
    files: ['**/*.ts'],
    extends: [
      eslint.configs.recommended,
      tseslint.configs.recommended,
      tseslint.configs.stylistic,
      angular.configs.tsRecommended,
    ],
    processor: angular.processInlineTemplates,
    rules: {
      '@angular-eslint/directive-selector': [
        'off',
      ],
      '@angular-eslint/component-selector': [
        'off',
      ],
      '@angular-eslint/no-output-on-prefix': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      '@angular-eslint/prefer-inject': 'off',
      '@angular-eslint/template/label-has-associated-control': 'off',
      '@typescript-eslint/class-literal-property-style': 'off',
      '@typescript-eslint/no-inferrable-types': 'off',
    },
  },
  {
    files: ['**/*.html'],
    extends: [
      angular.configs.templateRecommended,
      angular.configs.templateAccessibility,
    ],
    rules: {
      '@angular-eslint/template/label-has-associated-control': 'off',
    },
  }
]);
