import { mount } from "svelte";
import App from "./App.svelte";
import { settleLanguage, useLanguageStrategies } from "./lib/language";
import { m } from "./paraglide/messages.js";
import "./app.css";

useLanguageStrategies();
settleLanguage();
document.title = m.app_name();
mount(App, { target: document.getElementById("app")! });
