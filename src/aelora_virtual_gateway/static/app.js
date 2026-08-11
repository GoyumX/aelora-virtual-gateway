let state;
const $ = (id) => document.getElementById(id);
const fmtPower = (value) => `${(Math.abs(value || 0) / 1000).toFixed(2)} kW`;

function notice(message, error = false) {
  const node = $("notice");
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
  $("gateway-dot").className = `dot${state.gateway.enrolled && plant.publishingEnabled ? " online" : ""}`;
  $("gateway-status").textContent = state.gateway.enrolled ? (plant.publishingEnabled ? "Enrolled and publishing" : "Enrolled · publishing paused") : "Not enrolled with Aelora";
  $("enrollment-badge").textContent = state.gateway.enrolled ? "Enrolled" : "Not enrolled";
  $("enrollment-badge").className = `badge${state.gateway.enrolled ? "" : " warning"}`;
  $("aelora-url").textContent = state.gateway.aeloraBaseUrl;
  $("gateway-id").textContent = state.gateway.gatewayId || "—";
  $("pending-batches").textContent = state.gateway.pendingBatches;
  $("metric-solar").textContent = fmtPower(latest?.pvPowerW);
  $("metric-load").textContent = fmtPower(latest?.loadPowerW);
  $("metric-battery").textContent = `${latest?.batterySocPct?.toFixed(0) || 0}% · ${fmtPower(latest?.batteryPowerW)}`;
  $("metric-grid").textContent = `${(latest?.gridPowerW || 0) >= 0 ? "Import " : "Export "}${fmtPower(latest?.gridPowerW)}`;
  $("weather").value = plant.environment.weather;
  $("hour").value = plant.environment.hourOfDay;
  $("hour-output").textContent = `${String(Math.floor(plant.environment.hourOfDay)).padStart(2, "0")}:${plant.environment.hourOfDay % 1 ? "30" : "00"}`;
  $("temperature").value = plant.environment.ambientTemperatureC;
  $("load").value = plant.loadPowerW;
  $("publishing-enabled").checked = plant.publishingEnabled;
  $("publish-interval").value = plant.publishIntervalSec;
  $("publishing-badge").textContent = plant.publishingEnabled ? "Running" : "Paused";
  $("publishing-badge").className = `badge${plant.publishingEnabled ? "" : " warning"}`;
  $("scenario-badge").textContent = state.scenario?.code?.replaceAll("_", " ") || "None";
  $("scenario-badge").className = `badge${state.scenario ? "" : " warning"}`;
  $("scenario-detail").textContent = state.scenario ? `Active until ${new Date(state.scenario.endsAt).toLocaleString()}. The baseline plant will be restored automatically.` : "No timed scenario is active.";
  $("outbound-preview").textContent = state.outbound ? JSON.stringify(state.outbound, null, 2) : "No outbound request yet.";
  $("array-list").innerHTML = plant.arrays.map(arrayCard).join("");
  $("core-devices").innerHTML = [coreCard(plant.inverter, plant.inverter, ` · cap ${fmtPower(plant.inverter.maxAcPowerW)}`), coreCard(plant.battery, plant.battery, ` · ${plant.battery.stateOfChargePct.toFixed(0)}%`), coreCard(plant.grid, plant.grid)].join("");
}

async function refresh() { state = await api("/api/state"); render(); }
async function mutate(path, body, method = "PATCH") { await api(path, { method, body: JSON.stringify(body) }); await refresh(); }

document.addEventListener("click", async (event) => {
  const target = event.target.closest("button"); if (!target) return;
  try {
    if (target.dataset.control) await mutate(`/api/devices/${target.dataset.control}/control`, { [target.dataset.key]: target.dataset.value === "true" });
    if (target.dataset.delete) { await api(`/api/arrays/${target.dataset.delete}`, { method: "DELETE" }); await refresh(); }
  } catch (error) { notice(error.message, true); }
});
document.addEventListener("change", async (event) => {
  const target = event.target;
  if (!target.dataset.range) return;
  try { await mutate(`/api/devices/${target.dataset.range}/control`, { [target.dataset.key]: Number(target.value) }); } catch (error) { notice(error.message, true); }
});

$("hour").addEventListener("input", (event) => { const value = Number(event.target.value); $("hour-output").textContent = `${String(Math.floor(value)).padStart(2, "0")}:${value % 1 ? "30" : "00"}`; });
$("show-add-array").addEventListener("click", () => $("add-array-form").classList.toggle("hidden"));
$("add-array-form").addEventListener("submit", async (event) => { event.preventDefault(); try { await mutate("/api/arrays", { externalId: $("array-id").value, name: $("array-name").value, panelCount: Number($("array-count").value), ratedPowerW: Number($("array-watts").value) }, "POST"); event.target.reset(); event.target.classList.add("hidden"); notice("Solar array added."); } catch (error) { notice(error.message, true); } });
$("save-environment").addEventListener("click", async () => { try { await mutate("/api/environment", { weather: $("weather").value, hourOfDay: Number($("hour").value), ambientTemperatureC: Number($("temperature").value) }); await mutate("/api/load", { loadPowerW: Number($("load").value) }); notice("Virtual conditions applied."); } catch (error) { notice(error.message, true); } });
$("save-publishing").addEventListener("click", async () => { try { await mutate("/api/publishing", { enabled: $("publishing-enabled").checked, intervalSec: Number($("publish-interval").value) }); notice("Publishing settings saved."); } catch (error) { notice(error.message, true); } });
$("enrollment-form").addEventListener("submit", async (event) => { event.preventDefault(); try { await mutate("/api/enroll", { token: $("enrollment-token").value }, "POST"); $("enrollment-token").value = ""; notice("Gateway enrolled with Aelora."); } catch (error) { notice(error.message, true); } });
$("show-credential-form").addEventListener("click", () => $("credential-form").classList.toggle("hidden"));
$("credential-form").addEventListener("submit", async (event) => { event.preventDefault(); try { await mutate("/api/identity/credential", { credential: $("rotated-credential").value }); $("rotated-credential").value = ""; event.target.classList.add("hidden"); notice("Rotated credential saved locally. The next accepted request will activate it in Aelora."); } catch (error) { notice(error.message, true); } });
$("start-scenario").addEventListener("click", async () => { try { await mutate("/api/scenarios", { code: $("scenario-code").value, durationSec: Number($("scenario-duration").value) }, "POST"); notice("Timed scenario started."); } catch (error) { notice(error.message, true); } });
$("stop-scenario").addEventListener("click", async () => { try { await api("/api/scenarios/current", { method: "DELETE" }); await refresh(); notice("Scenario stopped and baseline restored."); } catch (error) { notice(error.message, true); } });
$("tick-now").addEventListener("click", async () => { try { await api("/api/tick", { method: "POST" }); await refresh(); notice("Simulation advanced by one tick."); } catch (error) { notice(error.message, true); } });
$("publish-now").addEventListener("click", async () => { try { const result = await api("/api/publish-now", { method: "POST" }); await refresh(); notice(result.published ? "Batch accepted by Aelora." : "Aelora unavailable; batch buffered locally.", !result.published); } catch (error) { notice(error.message, true); } });
$("reset-plant").addEventListener("click", async () => { if (!confirm("Reset the virtual plant to defaults?")) return; try { await api("/api/reset", { method: "POST" }); await refresh(); notice("Virtual plant reset."); } catch (error) { notice(error.message, true); } });

refresh().catch((error) => notice(error.message, true));
window.setInterval(() => refresh().catch(() => {}), 3000);
