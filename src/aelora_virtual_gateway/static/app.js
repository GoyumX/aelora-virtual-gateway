let state;
const $ = (id) => document.getElementById(id);
const fmtPower = (value) => `${(Math.abs(value || 0) / 1000).toFixed(2)} kW`;
const numberValue = (id, multiplier = 1) => Number($(id)?.value ?? 0) * multiplier;
const dirtyInputs = new Set();
const syncValue = (id, value) => { const node = $(id); if (!node || dirtyInputs.has(id)) return; node.value = value; };
const syncChecked = (id, value) => { const node = $(id); if (!node || dirtyInputs.has(id)) return; node.checked = value; };
const syncText = (id, value) => { const node = $(id); if (node) node.textContent = value; };
const syncClassName = (id, value) => { const node = $(id); if (node) node.className = value; };
const syncDisabled = (id, value) => { const node = $(id); if (node) node.disabled = value; };
const syncToggleClass = (id, name, enabled) => { const node = $(id); if (node) node.classList.toggle(name, enabled); };
const syncHtml = (id, value) => { const node = $(id); if (node) node.innerHTML = value; };
const displayedValue = (id, fallback) => { const node = $(id); return dirtyInputs.has(id) && node ? node.value : fallback; };
const fieldValue = (id, fallback = "") => $(id)?.value ?? fallback;
const checkedValue = (id, fallback = false) => $(id)?.checked ?? fallback;
const forceValue = (id, value) => { const node = $(id); if (node) node.value = value; };
const on = (id, eventName, listener) => { const node = $(id); if (node) node.addEventListener(eventName, listener); };
const markClean = (...ids) => ids.forEach((id) => dirtyInputs.delete(id));
const defaultReplayHourValue = () => {
  const start = new Date();
  start.setUTCMinutes(0, 0, 0);
  start.setUTCHours(start.getUTCHours() - 1);
  const local = new Date(start.getTime() - start.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
};

function notice(message, error = false) {
  const node = $("notice");
  if (!node) return;
  node.textContent = message;
  node.className = `notice show${error ? " error" : ""}`;
  window.setTimeout(() => { node.className = "notice"; node.textContent = ""; }, 5000);
}

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const body = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.detail || "Gateway request failed");
  return body;
}

function deviceObservation(id) { return state.latest?.devices.find((item) => item.externalId === id); }
function badge(status) { return `<span class="badge ${status === "ONLINE" ? "" : "offline"}">${status.toLowerCase()}</span>`; }

function arrayCard(array) {
  const observation = deviceObservation(array.externalId);
  return `<div class="device"><div class="device-head"><div><h3>${array.name}</h3><p>${array.externalId} · ${array.panelCount} × ${array.ratedPowerW} W · ${fmtPower(observation?.metrics?.powerW)}</p></div>${badge(observation?.connectivityStatus || "NEVER_SEEN")}</div><div class="device-actions"><button class="button mini" data-control="${array.externalId}" data-key="communicationsEnabled" data-value="${!array.communicationsEnabled}">Comms ${array.communicationsEnabled ? "off" : "on"}</button><button class="button mini" data-control="${array.externalId}" data-key="operating" data-value="${!array.operating}">${array.operating ? "Stop" : "Start"} operation</button><button class="button mini" data-delete="${array.externalId}">Remove</button></div><div class="sliders"><label>Efficiency ${array.efficiencyPct}%<input type="range" min="0" max="100" value="${array.efficiencyPct}" data-range="${array.externalId}" data-key="efficiencyPct" /></label><label>Shade ${array.shadingPct}%<input type="range" min="0" max="100" value="${array.shadingPct}" data-range="${array.externalId}" data-key="shadingPct" /></label><label>Soiling ${array.soilingPct}%<input type="range" min="0" max="100" value="${array.soilingPct}" data-range="${array.externalId}" data-key="soilingPct" /></label></div></div>`;
}

function coreCard(device, stateObject, extra = "") {
  const observation = deviceObservation(device.externalId);
  return `<div class="device"><div class="device-head"><div><h3>${device.name}</h3><p>${observation?.kind?.toLowerCase().replaceAll("_", " ") || "device"} · ${observation?.operationalState?.toLowerCase() || "unknown"}${extra}</p></div>${badge(observation?.connectivityStatus || "NEVER_SEEN")}</div><div class="device-actions"><button class="button mini" data-control="${device.externalId}" data-key="communicationsEnabled" data-value="${!device.communicationsEnabled}">Comms ${device.communicationsEnabled ? "off" : "on"}</button>${stateObject.operating !== undefined ? `<button class="button mini" data-control="${device.externalId}" data-key="operating" data-value="${!stateObject.operating}">${stateObject.operating ? "Stop" : "Start"}</button>` : ""}${stateObject.available !== undefined ? `<button class="button mini" data-control="${device.externalId}" data-key="available" data-value="${!stateObject.available}">Grid ${stateObject.available ? "outage" : "restore"}</button>` : ""}</div></div>`;
}

function render() {
  const plant = state.plant;
  const latest = state.latest?.siteSnapshot;
  const localDate = state.clock?.localDateTime ? new Date(state.clock.localDateTime) : null;
  syncClassName("gateway-dot", `dot${state.gateway.enrolled && plant.publishingEnabled ? " online" : ""}`);
  syncText("gateway-status", state.gateway.enrolled ? (plant.publishingEnabled ? "Enrolled and publishing" : "Enrolled · publishing paused") : "Not enrolled with Aelora");
  syncText("enrollment-badge", state.gateway.enrolled ? "Enrolled" : "Not enrolled");
  syncClassName("enrollment-badge", `badge${state.gateway.enrolled ? "" : " warning"}`);
  syncText("aelora-url", state.gateway.aeloraBaseUrl);
  syncText("gateway-id", state.gateway.gatewayId || "—");
  syncText("pending-batches", state.gateway.pendingBatches);
  syncText("metric-time", localDate ? localDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—");
  syncText("metric-date", localDate ? `${localDate.toLocaleDateString([], { weekday: "short", year: "numeric", month: "short", day: "numeric" })} · ${state.clock.timezone} · ${state.clock.mode.toLowerCase()} mode` : "—");
  syncText("metric-solar", fmtPower(latest?.pvPowerW));
  syncText("metric-load", fmtPower(latest?.loadPowerW));
  syncText("metric-battery", `${latest?.batterySocPct?.toFixed(1) || 0}% · ${fmtPower(latest?.batteryPowerW)}`);
  syncText("metric-grid", `${(latest?.gridPowerW || 0) >= 0 ? "Import " : "Export "}${fmtPower(latest?.gridPowerW)}`);
  syncValue("clock-mode", plant.environment.clockMode);
  syncValue("weather", plant.environment.weather);
  syncValue("hour", plant.environment.hourOfDay);
  const displayedClockMode = displayedValue("clock-mode", plant.environment.clockMode);
  syncDisabled("hour", displayedClockMode === "SYSTEM");
  syncToggleClass("manual-hour-label", "disabled-control", displayedClockMode === "SYSTEM");
  const displayedHour = Number(displayedValue("hour", plant.environment.hourOfDay));
  syncText("hour-output", `${String(Math.floor(displayedHour)).padStart(2, "0")}:${displayedHour % 1 ? "30" : "00"}`);
  syncValue("temperature", plant.environment.ambientTemperatureC);
  syncValue("cloud-variability", plant.environment.cloudVariabilityPct);
  syncValue("variation-seed", plant.environment.variationSeed);
  syncValue("load-mode", plant.loadMode);
  syncValue("load-fixed", plant.loadPowerW);
  syncValue("load-min", plant.loadMinPowerW);
  syncValue("load-max", plant.loadMaxPowerW);
  const displayedLoadMode = displayedValue("load-mode", plant.loadMode);
  syncDisabled("load-fixed", displayedLoadMode === "DYNAMIC");
  syncDisabled("load-min", displayedLoadMode === "FIXED");
  syncDisabled("load-max", displayedLoadMode === "FIXED");
  syncValue("battery-capacity", (plant.battery.capacityWh / 1000).toFixed(1));
  syncValue("battery-soc", plant.battery.stateOfChargePct.toFixed(1));
  syncValue("battery-min-soc", plant.battery.minSocPct);
  syncValue("battery-max-soc", plant.battery.maxSocPct);
  syncValue("battery-charge-power", (plant.battery.maxChargePowerW / 1000).toFixed(1));
  syncValue("battery-discharge-power", (plant.battery.maxDischargePowerW / 1000).toFixed(1));
  syncValue("grid-voltage", plant.grid.voltageV);
  syncValue("grid-voltage-variability", plant.grid.voltageVariabilityPct);
  syncValue("grid-frequency", plant.grid.frequencyHz);
  syncValue("grid-frequency-variability", plant.grid.frequencyVariabilityHz);
  syncChecked("publishing-enabled", plant.publishingEnabled);
  syncValue("publish-interval", plant.publishIntervalSec);
  if (!fieldValue("replay-hour-start")) syncValue("replay-hour-start", defaultReplayHourValue());
  syncText("publishing-badge", plant.publishingEnabled ? "Running" : "Paused");
  syncClassName("publishing-badge", `badge${plant.publishingEnabled ? "" : " warning"}`);
  syncText("scenario-badge", state.scenario?.code?.replaceAll("_", " ") || "None");
  syncClassName("scenario-badge", `badge${state.scenario ? "" : " warning"}`);
  syncText("scenario-detail", state.scenario ? `Active until ${new Date(state.scenario.endsAt).toLocaleString()}. The baseline plant will be restored automatically.` : "No timed scenario is active.");
  syncText("outbound-preview", state.outbound ? JSON.stringify(state.outbound, null, 2) : "No outbound request yet.");
  syncHtml("array-list", plant.arrays.map(arrayCard).join(""));
  syncHtml("core-devices", [coreCard(plant.inverter, plant.inverter, ` · cap ${fmtPower(plant.inverter.maxAcPowerW)}`), coreCard(plant.battery, plant.battery, ` · ${plant.battery.stateOfChargePct.toFixed(1)}% · ${(plant.battery.capacityWh / 1000).toFixed(1)} kWh`), coreCard(plant.grid, plant.grid, ` · ${latest?.gridVoltageV?.toFixed(1) || 0} V · ${latest?.frequencyHz?.toFixed(2) || 0} Hz`)].join(""));
}

async function refresh() { state = await api("/api/state"); render(); }
async function mutate(path, body, method = "PATCH", cleanIds = []) {
  await api(path, { method, body: JSON.stringify(body) });
  markClean(...cleanIds);
  await refresh();
}

document.addEventListener("click", async (event) => {
  const target = event.target.closest("button"); if (!target) return;
  try {
    if (target.dataset.control) await mutate(`/api/devices/${target.dataset.control}/control`, { [target.dataset.key]: target.dataset.value === "true" });
    if (target.dataset.delete) { await api(`/api/arrays/${target.dataset.delete}`, { method: "DELETE" }); await refresh(); }
  } catch (error) { notice(error.message, true); }
});
document.addEventListener("input", (event) => { if (event.target.id) dirtyInputs.add(event.target.id); });
document.addEventListener("change", async (event) => {
  const target = event.target;
  if (target.id) dirtyInputs.add(target.id);
  if (!target.dataset.range) return;
  try { await mutate(`/api/devices/${target.dataset.range}/control`, { [target.dataset.key]: Number(target.value) }); } catch (error) { notice(error.message, true); }
});

on("hour", "input", (event) => { const value = Number(event.target.value); syncText("hour-output", `${String(Math.floor(value)).padStart(2, "0")}:${value % 1 ? "30" : "00"}`); });
on("clock-mode", "change", (event) => { const system = event.target.value === "SYSTEM"; syncDisabled("hour", system); syncToggleClass("manual-hour-label", "disabled-control", system); });
on("load-mode", "change", (event) => { const dynamic = event.target.value === "DYNAMIC"; syncDisabled("load-fixed", dynamic); syncDisabled("load-min", !dynamic); syncDisabled("load-max", !dynamic); });
on("show-add-array", "click", () => syncToggleClass("add-array-form", "hidden", !$("add-array-form")?.classList.contains("hidden")));
on("add-array-form", "submit", async (event) => { event.preventDefault(); try { await mutate("/api/arrays", { externalId: fieldValue("array-id"), name: fieldValue("array-name"), panelCount: Number(fieldValue("array-count", 0)), ratedPowerW: Number(fieldValue("array-watts", 0)) }, "POST"); event.target.reset(); event.target.classList.add("hidden"); notice("Solar array added."); } catch (error) { notice(error.message, true); } });
on("save-environment", "click", async () => { try { await mutate("/api/environment", { clockMode: fieldValue("clock-mode"), weather: fieldValue("weather"), hourOfDay: numberValue("hour"), ambientTemperatureC: numberValue("temperature"), cloudVariabilityPct: numberValue("cloud-variability"), variationSeed: numberValue("variation-seed") }, "PATCH", ["clock-mode", "weather", "hour", "temperature", "cloud-variability", "variation-seed"]); notice("Virtual weather and clock settings applied."); } catch (error) { notice(error.message, true); } });
on("save-load", "click", async () => { try { await mutate("/api/load", { loadMode: fieldValue("load-mode"), loadPowerW: numberValue("load-fixed"), loadMinPowerW: numberValue("load-min"), loadMaxPowerW: numberValue("load-max") }, "PATCH", ["load-mode", "load-fixed", "load-min", "load-max"]); notice("Household demand settings saved."); } catch (error) { notice(error.message, true); } });
on("save-battery", "click", async () => { try { await mutate("/api/battery", { capacityWh: numberValue("battery-capacity", 1000), stateOfChargePct: numberValue("battery-soc"), minSocPct: numberValue("battery-min-soc"), maxSocPct: numberValue("battery-max-soc"), maxChargePowerW: numberValue("battery-charge-power", 1000), maxDischargePowerW: numberValue("battery-discharge-power", 1000) }, "PATCH", ["battery-capacity", "battery-soc", "battery-min-soc", "battery-max-soc", "battery-charge-power", "battery-discharge-power"]); notice("Battery capacity and operating limits saved."); } catch (error) { notice(error.message, true); } });
on("save-grid", "click", async () => { try { await mutate(`/api/devices/${state.plant.grid.externalId}/control`, { voltageV: numberValue("grid-voltage"), voltageVariabilityPct: numberValue("grid-voltage-variability"), frequencyHz: numberValue("grid-frequency"), frequencyVariabilityHz: numberValue("grid-frequency-variability") }, "PATCH", ["grid-voltage", "grid-voltage-variability", "grid-frequency", "grid-frequency-variability"]); notice("Grid signal dynamics saved."); } catch (error) { notice(error.message, true); } });
on("save-publishing", "click", async () => { try { await mutate("/api/publishing", { enabled: checkedValue("publishing-enabled"), intervalSec: Number(fieldValue("publish-interval", 30)) }, "PATCH", ["publishing-enabled", "publish-interval"]); notice("Publishing settings saved."); } catch (error) { notice(error.message, true); } });
on("replay-hour", "click", async () => { if (!confirm("Replay one completed simulator hour into Aelora? This writes SIMULATED telemetry and can never promote the model.")) return; try { const startAt = new Date(fieldValue("replay-hour-start")).toISOString(); const result = await api("/api/development/replay-hour", { method: "POST", body: JSON.stringify({ startAt }) }); await refresh(); notice(`${result.accepted}/${result.attempted} simulated samples accepted; ${result.buffered} buffered.` , result.buffered > 0); } catch (error) { notice(error.message, true); } });
on("enrollment-form", "submit", async (event) => { event.preventDefault(); try { await mutate("/api/enroll", { token: fieldValue("enrollment-token") }, "POST"); forceValue("enrollment-token", ""); notice("Gateway enrolled with Aelora."); } catch (error) { notice(error.message, true); } });
on("show-credential-form", "click", () => syncToggleClass("credential-form", "hidden", !$("credential-form")?.classList.contains("hidden")));
on("credential-form", "submit", async (event) => { event.preventDefault(); try { await mutate("/api/identity/credential", { credential: fieldValue("rotated-credential") }); forceValue("rotated-credential", ""); event.target.classList.add("hidden"); notice("Rotated credential saved locally. The next accepted request will activate it in Aelora."); } catch (error) { notice(error.message, true); } });
on("start-scenario", "click", async () => { try { await mutate("/api/scenarios", { code: fieldValue("scenario-code"), durationSec: Number(fieldValue("scenario-duration", 300)) }, "POST"); notice("Timed scenario started."); } catch (error) { notice(error.message, true); } });
on("stop-scenario", "click", async () => { try { await api("/api/scenarios/current", { method: "DELETE" }); await refresh(); notice("Scenario stopped and baseline restored."); } catch (error) { notice(error.message, true); } });
on("tick-now", "click", async () => { try { await api("/api/tick", { method: "POST" }); await refresh(); notice("Simulation advanced by one tick."); } catch (error) { notice(error.message, true); } });
on("publish-now", "click", async () => { try { const result = await api("/api/publish-now", { method: "POST" }); await refresh(); notice(result.published ? "Batch accepted by Aelora." : "Aelora unavailable; batch buffered locally.", !result.published); } catch (error) { notice(error.message, true); } });
on("reset-plant", "click", async () => { if (!confirm("Reset the virtual plant to defaults?")) return; try { await api("/api/reset", { method: "POST" }); dirtyInputs.clear(); await refresh(); notice("Virtual plant reset."); } catch (error) { notice(error.message, true); } });

refresh().catch((error) => notice(error.message, true));
window.setInterval(() => refresh().catch(() => {}), 3000);
