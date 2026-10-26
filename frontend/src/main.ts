import { mount } from "svelte";
import App from "./App.svelte";
import { settleLanguage, useLanguageStrategies } from "./lib/language";
import { namePage } from "./lib/page";
import { applyTheme, chosenTheme } from "./lib/theme";
import { m } from "./paraglide/messages.js";
import "./app.css";

useLanguageStrategies();
settleLanguage();
namePage(m.app_name());
applyTheme(chosenTheme());
mount(App, { target: document.getElementById("app")! });
