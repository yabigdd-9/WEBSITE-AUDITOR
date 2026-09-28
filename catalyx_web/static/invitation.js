(() => {
  const field = document.querySelector('[name="invitation_token"]');
  if (!field || !window.location.hash) return;

  try {
    field.value = decodeURIComponent(window.location.hash.slice(1));
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  } catch {
    field.value = "";
  }
})();
