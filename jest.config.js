/** @type {import('jest').Config} */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>/packages', '<rootDir>/apps', '<rootDir>/tests'],
  testMatch: ['**/__tests__/**/*.test.ts', '**/*.conformance.test.ts'],
  moduleNameMapper: {
    '^@messenger/protocol$': '<rootDir>/packages/protocol/ts/src/index.ts',
    '^@messenger/crypto$': '<rootDir>/packages/crypto/ts/src/index.ts',
  },
};
