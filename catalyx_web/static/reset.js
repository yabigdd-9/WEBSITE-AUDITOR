"use strict";

const tokenInput = document.getElementById("reset-token");
const resetButton = document.getElementById("reset-button");
const hint = document.getElementById("reset-hint");
const fragment = window.location.hash.slice(1);

if (tokenInput && resetButton && hint && fragment) {
  tokenInput.value = fragment;
  resetButton.disabled = false;
  hint.textContent = "Your one-time link is ready. Choose a new password to continue.";
  window.history.replaceState(null, "", window.location.pathname);
}
