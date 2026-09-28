"use strict";

const tokenInput = document.getElementById("verification-token");
const verifyButton = document.getElementById("verify-button");
const hint = document.getElementById("verification-hint");
const fragment = window.location.hash.slice(1);

if (tokenInput && verifyButton && fragment) {
  tokenInput.value = fragment;
  verifyButton.disabled = false;
  hint.textContent = "Your one-time link is ready. Confirm to finish verification.";
  window.history.replaceState(null, "", window.location.pathname);
}
