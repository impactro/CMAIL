"use strict";
const choices = Array.from(document.querySelectorAll('input[name="provider"]'));
const oauth = document.querySelector('[data-provider-panel="oauth"]');
const imap = document.querySelector('[data-provider-panel="imap"]');
const tenant = document.querySelector('[data-outlook-only]');
function syncProvider() {
  const provider = choices.find(item => item.checked)?.value || "outlook";
  const isImap = provider === "imap";
  oauth.hidden = isImap;
  imap.hidden = !isImap;
  tenant.hidden = provider !== "outlook";
  oauth.querySelectorAll("input").forEach(input => { input.required = !isImap && (!input.closest('[data-outlook-only]') || provider === "outlook"); });
  imap.querySelectorAll("input,select").forEach(input => { input.required = isImap; });
}
choices.forEach(item => item.addEventListener("change", syncProvider));
syncProvider();
