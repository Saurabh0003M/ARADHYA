module.exports = {
  env: {
    es6: true,
    jest: true,
    browser: true
  },
  extends: ["react-app"],
  rules: {
    "no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
    "no-console": "off",
  },
};
