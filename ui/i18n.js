/* Переводы интерфейса. Источник — английский текст в HTML (data-i18n) и STR ниже; словари — /ui/i18n/<lang>.json */
"use strict";
const LANGS = { en: "English", de: "Deutsch", fr: "Français", es: "Español", it: "Italiano", pl: "Polski",
  cs: "Čeština", sk: "Slovenčina", uk: "Українська", ru: "Русский" };
const I18N = { lang: "en", dict: {}, en: {} };

async function loadLang(lang) {
  lang = LANGS[lang] ? lang : "en";
  const get = async (l) => { try { const r = await fetch(`/ui/i18n/${l}.json`, { cache: "no-store" }); return r.ok ? await r.json() : {}; } catch { return {}; } };
  if (!Object.keys(I18N.en).length) I18N.en = await get("en");
  I18N.dict = lang === "en" ? I18N.en : await get(lang);
  I18N.lang = lang;
  document.documentElement.lang = lang;
  applyI18n();
}

function T(key, vars) {
  let s = I18N.dict[key] ?? I18N.en[key] ?? (typeof STR !== "undefined" ? STR[key] : undefined) ?? key;
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] ?? m));
  return s;
}

function applyI18n(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => {
    if (el.dataset.en === undefined) el.dataset.en = el.textContent;
    const k = el.dataset.i18n;
    el.textContent = I18N.dict[k] ?? I18N.en[k] ?? el.dataset.en;
  });
  root.querySelectorAll("[data-i18n-ph]").forEach((el) => {
    if (el.dataset.enPh === undefined) el.dataset.enPh = el.placeholder;
    const k = el.dataset.i18nPh;
    el.placeholder = I18N.dict[k] ?? I18N.en[k] ?? el.dataset.enPh;
  });
  root.querySelectorAll("[data-i18n-title]").forEach((el) => {
    const k = el.dataset.i18nTitle;
    const v = I18N.dict[k] ?? I18N.en[k] ?? (typeof STR !== "undefined" ? STR[k] : "") ?? "";
    el.title = v; el.setAttribute("aria-label", v);
  });
  if (typeof onLangApplied === "function") onLangApplied();
}
