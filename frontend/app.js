/**
 * FLO — Factory Logistics Optimizer Front-End Engine
 * Canvas 2D Renderer & Real-time State Controller (Optimized & Responsive)
 */

const CORE_URL = 'http://127.0.0.1:8000';
const FACTORY_URL = 'http://127.0.0.1:8001';

let canvas, ctx;
let simState = { agvs: [], tasks: [] };
let floState = { nodes: [], edges: [], events: [], metrics: {}, baseline: {} };
let lastAgvJson = '';
let lastTaskJson = '';
let lastEventJson = '';

document.addEventListener('DOMContentLoaded', () => {
  canvas = document.getElementById('factoryCanvas');
  if (canvas) {
    ctx = canvas.getContext('2d');
  }
  startPolling();
  requestAnimationFrame(animLoop);
});

function startPolling() {
  fetchState();
  setInterval(fetchState, 200); // 5Hz state sync loop
}

async function fetchState() {
  try {
    const [resSim, resFlo] = await Promise.all([
      fetch(`${FACTORY_URL}/api/simulator_state`),
      fetch(`${CORE_URL}/api/state`)
    ]);

    if (resSim.ok) simState = await resSim.json();
    if (resFlo.ok) floState = await resFlo.json();

    updateDOM();
  } catch (err) {
    console.warn("API Connection waiting...", err);
  }
}

/* ----------------------------------------------------
 * ANIMATION LOOP (Smooth 60 FPS Canvas Redraw)
 * ---------------------------------------------------- */
function animLoop() {
  renderCanvas();
  requestAnimationFrame(animLoop);
}

/* ----------------------------------------------------
 * DOM UPDATES (Throttled for zero UI lag)
 * ---------------------------------------------------- */
function updateDOM() {
  renderKPIs();
  
  const agvJson = JSON.stringify(simState.agvs);
  if (agvJson !== lastAgvJson) {
    renderAGVTable();
    lastAgvJson = agvJson;
  }

  const taskJson = JSON.stringify(simState.tasks);
  if (taskJson !== lastTaskJson) {
    renderTaskTable();
    lastTaskJson = taskJson;
  }

  const evtJson = JSON.stringify((floState.events || []).slice(0, 10));
  if (evtJson !== lastEventJson) {
    renderEvents();
    lastEventJson = evtJson;
  }
}

/* ----------------------------------------------------
 * CANVAS 2D FACTORY FLOOR RENDERER
 * ---------------------------------------------------- */
function renderCanvas() {
  if (!ctx || !canvas) return;

  // Clear Canvas
  ctx.fillStyle = '#f8fafc';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Draw Subtle Grid
  ctx.strokeStyle = '#e2e8f0';
  ctx.lineWidth = 1;
  for (let x = 0; x < canvas.width; x += 40) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
  }
  for (let y = 0; y < canvas.height; y += 40) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke();
  }

  // Build Node Map
  const nodeMap = {};
  if (floState.nodes) {
    floState.nodes.forEach(n => nodeMap[n.id] = n);
  }

  // 1. Draw Edges / Corridors
  if (floState.edges) {
    floState.edges.forEach(edge => {
      const u = nodeMap[edge.source];
      const v = nodeMap[edge.destination];
      if (!u || !v) return;

      ctx.beginPath();
      ctx.moveTo(u.x, u.y);
      ctx.lineTo(v.x, v.y);

      if (edge.blocked) {
        ctx.strokeStyle = '#dc2626';
        ctx.lineWidth = 4;
        ctx.setLineDash([6, 6]);
      } else if (edge.congestion > 0.5) {
        ctx.strokeStyle = '#d97706';
        ctx.lineWidth = 3.5;
        ctx.setLineDash([4, 4]);
      } else {
        ctx.strokeStyle = '#cbd5e1';
        ctx.lineWidth = 2;
        ctx.setLineDash([]);
      }
      ctx.stroke();
      ctx.setLineDash([]);
    });
  }

  // 2. Draw Machine & Facility Blocks
  if (floState.nodes) {
    floState.nodes.forEach(n => {
      ctx.save();
      if (n.node_type === 'warehouse') {
        drawFacilityBox(n.x, n.y, 110, 60, '#2563eb', 'RAW WAREHOUSE');
      } else if (n.node_type === 'machine') {
        drawFacilityBox(n.x, n.y, 90, 50, '#7c3aed', n.name);
      } else if (n.node_type === 'assembly') {
        drawFacilityBox(n.x, n.y, 100, 50, '#db2777', 'ASSEMBLY');
      } else if (n.node_type === 'dispatch') {
        drawFacilityBox(n.x, n.y, 110, 60, '#16a34a', 'DISPATCH');
      } else if (n.node_type === 'charging') {
        drawFacilityBox(n.x, n.y, 90, 45, '#ca8a04', '⚡ CHARGER');
      } else if (n.node_type === 'junction') {
        ctx.fillStyle = '#94a3b8';
        ctx.beginPath();
        ctx.arc(n.x, n.y, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#64748b';
        ctx.font = '10px Arial';
        ctx.fillText(n.id, n.x + 6, n.y - 6);
      }
      ctx.restore();
    });
  }

  // 3. Draw AGV Active Path Traces
  if (simState.agvs) {
    simState.agvs.forEach(agv => {
      if (agv.current_route && agv.current_route.length > 1) {
        ctx.beginPath();
        ctx.strokeStyle = agv.status === 'LOW_BATTERY' ? '#d97706' : '#0284c7';
        ctx.lineWidth = 2;
        ctx.setLineDash([4, 4]);

        for (let i = agv.route_index; i < agv.current_route.length; i++) {
          const nid = agv.current_route[i];
          const nd = nodeMap[nid];
          if (nd) {
            if (i === agv.route_index) ctx.moveTo(agv.x, agv.y);
            else ctx.lineTo(nd.x, nd.y);
          }
        }
        ctx.stroke();
        ctx.setLineDash([]);
      }
    });
  }

  // 4. Draw AGVs with Authoritative Status Color & Co-location Radial Offsets
  if (simState.agvs) {
    const posGroups = {};
    simState.agvs.forEach(agv => {
      const key = `${Math.round(agv.x / 20)}_${Math.round(agv.y / 20)}`;
      if (!posGroups[key]) posGroups[key] = [];
      posGroups[key].push(agv);
    });

    simState.agvs.forEach(agv => {
      const key = `${Math.round(agv.x / 20)}_${Math.round(agv.y / 20)}`;
      const group = posGroups[key] || [agv];
      const indexInGroup = group.indexOf(agv);

      let drawX = agv.x;
      let drawY = agv.y;

      // Radial offset for co-located AGVs
      if (group.length > 1) {
        const angle = (indexInGroup / group.length) * Math.PI * 2 - Math.PI / 2;
        const radius = 18;
        drawX += Math.cos(angle) * radius;
        drawY += Math.sin(angle) * radius;
      }

      ctx.save();

      // Authoritative Status Color Mapping
      let color = '#16a34a'; // AVAILABLE -> Green
      if (agv.status === 'FAILED') color = '#dc2626'; // Red
      else if (agv.status === 'LOW_BATTERY') color = '#ea580c'; // Orange
      else if (agv.status === 'CHARGING') color = '#ca8a04'; // Yellow
      else if (agv.status.includes('MOVING')) color = '#2563eb'; // Blue

      // AGV Body Circle
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(drawX, drawY, 11, 0, Math.PI * 2);
      ctx.fill();

      // Inner Core
      ctx.fillStyle = '#ffffff';
      ctx.beginPath();
      ctx.arc(drawX, drawY, 5, 0, Math.PI * 2);
      ctx.fill();

      // Labels: AGV ID & Battery %
      ctx.fillStyle = '#1e293b';
      ctx.font = 'bold 10px Arial';
      ctx.fillText(agv.id, drawX - 14, drawY - 15);

      ctx.fillStyle = agv.battery < 20 ? '#dc2626' : '#15803d';
      ctx.font = 'bold 9px monospace';
      ctx.fillText(`${Math.round(agv.battery)}%`, drawX - 10, drawY + 22);

      ctx.restore();
    });
  }
}

function drawFacilityBox(x, y, width, height, color, label) {
  ctx.fillStyle = '#ffffff';
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.8;
  ctx.beginPath();
  ctx.roundRect(x - width/2, y - height/2, width, height, 6);
  ctx.fill();
  ctx.stroke();

  ctx.fillStyle = color;
  ctx.font = 'bold 10px Arial';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(label, x, y);
}

/* ----------------------------------------------------
 * UI DATA RENDERING
 * ---------------------------------------------------- */
function renderKPIs() {
  const m = floState.metrics || {};
  const completedCount = (simState.tasks || []).filter(t => t.status === 'COMPLETED').length;
  const pendingCount = (simState.tasks || []).filter(t => t.status !== 'COMPLETED').length;
  
  document.getElementById('kpiCompleted').innerText = completedCount;
  document.getElementById('kpiPending').innerText = pendingCount;
  document.getElementById('kpiAvgTime').innerText = m.avg_delivery_time ? `${m.avg_delivery_time.toFixed(1)}s` : '0s';
  document.getElementById('kpiGain').innerText = m.flo_efficiency_gain_pct ? `+${m.flo_efficiency_gain_pct.toFixed(1)}%` : '0%';
}

function renderAGVTable() {
  const tbody = document.getElementById('agvTableBody');
  if (!tbody || !simState.agvs) return;

  tbody.innerHTML = simState.agvs.map(agv => {
    let badgeClass = 'badge-available';
    if (agv.status === 'FAILED') badgeClass = 'badge-failed';
    else if (agv.status === 'LOW_BATTERY') badgeClass = 'badge-low';
    else if (agv.status === 'CHARGING') badgeClass = 'badge-charging';
    else if (agv.status.includes('MOVING')) badgeClass = 'badge-moving';

    const taskLabel = agv.status === 'AVAILABLE' ? '-' : (agv.current_task_id || '-');

    return `
      <tr>
        <td><strong>${agv.id}</strong></td>
        <td>${Math.round(agv.battery)}%</td>
        <td><span class="badge ${badgeClass}">${agv.status}</span></td>
        <td>${taskLabel}</td>
      </tr>
    `;
  }).join('');
}

function renderTaskTable() {
  const tbody = document.getElementById('taskTableBody');
  if (!tbody || !simState.tasks) return;

  // Filter out COMPLETED tasks from the active queue display so queue stays clean!
  const activeTasks = simState.tasks.filter(t => t.status !== 'COMPLETED');

  if (activeTasks.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 16px;">No active tasks in queue</td></tr>`;
    return;
  }

  tbody.innerHTML = activeTasks.map(t => {
    let prioClass = t.priority === 'URGENT' ? 'badge-urgent' : '';
    return `
      <tr>
        <td><strong>${t.task_id}</strong></td>
        <td>${t.pickup} → ${t.destination}</td>
        <td><span class="badge ${prioClass}">${t.priority}</span></td>
        <td>${t.status}</td>
        <td>${t.assigned_agv_id || '-'}</td>
      </tr>
    `;
  }).join('');
}

function renderEvents() {
  const container = document.getElementById('eventLog');
  if (!container || !floState.events) return;

  container.innerHTML = floState.events.slice(0, 10).map(e => `
    <div class="log-entry ${e.level}">
      <span style="color: var(--text-muted); margin-right: 6px;">[${e.timestamp}]</span>
      <strong>[${e.category}]</strong> ${e.message}
    </div>
  `).join('');
}

/* ----------------------------------------------------
 * SCENARIO CONTROLLERS & MODAL HANDLERS
 * ---------------------------------------------------- */

function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = 'flex';
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = 'none';
}

function openNewTaskModal() { openModal('taskModal'); }
function closeNewTaskModal() { closeModal('taskModal'); }

function openCongestionModal() { openModal('congestionModal'); }
function openBlockRouteModal() { openModal('blockModal'); }
function openLowBatteryModal() { openModal('lowBatteryModal'); }
function openFailAgvModal() { openModal('failModal'); }

async function submitAddCongestion() {
  const corridor = document.getElementById('congCorridor').value.split('_');
  await fetch(`${CORE_URL}/api/scenario/add_congestion`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ src: corridor[0], dst: corridor[1] })
  });
  closeModal('congestionModal');
}

async function submitRemoveCongestion() {
  const corridor = document.getElementById('congCorridor').value.split('_');
  await fetch(`${CORE_URL}/api/scenario/remove_congestion`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ src: corridor[0], dst: corridor[1] })
  });
  closeModal('congestionModal');
}

async function submitBlockRoute() {
  const corridor = document.getElementById('blockCorridor').value.split('_');
  await fetch(`${CORE_URL}/api/scenario/block_route`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ src: corridor[0], dst: corridor[1] })
  });
  closeModal('blockModal');
}

async function submitUnblockRoute() {
  const corridor = document.getElementById('blockCorridor').value.split('_');
  await fetch(`${CORE_URL}/api/scenario/unblock_route`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ src: corridor[0], dst: corridor[1] })
  });
  closeModal('blockModal');
}

async function submitLowBattery() {
  const agv_id = document.getElementById('batAgv').value;
  const battery = parseFloat(document.getElementById('batLevel').value);
  await fetch(`${CORE_URL}/api/scenario/low_battery_test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agv_id, battery })
  });
  closeModal('lowBatteryModal');
}

async function submitFailAGV() {
  const agv_id = document.getElementById('failAgv').value;
  await fetch(`${CORE_URL}/api/scenario/fail_agv`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agv_id })
  });
  closeModal('failModal');
}

async function submitRecoverAGV() {
  const agv_id = document.getElementById('failAgv').value;
  await fetch(`${CORE_URL}/api/scenario/recover_agv`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agv_id })
  });
  closeModal('failModal');
}

async function triggerUrgentTask() {
  try {
    const res = await fetch(`${CORE_URL}/api/task/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pickup: 'WAREHOUSE',
        destination: 'ASSY',
        priority: 'URGENT',
        weight: 30.0,
        deadline_seconds: 120.0
      })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    fetchState();
  } catch (err) {
    alert("CORE DISCONNECTED: Task could not be created.");
  }
}

async function submitNewTask(e) {
  e.preventDefault();
  try {
    const pickup = document.getElementById('taskPickup').value;
    const destination = document.getElementById('taskDest').value;
    const priority = document.getElementById('taskPriority').value;
    const weight = parseFloat(document.getElementById('taskWeight').value);

    const res = await fetch(`${FACTORY_URL}/api/task/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pickup, destination, priority, weight, deadline_seconds: 300 })
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    closeNewTaskModal();
    fetchState();
  } catch (err) {
    console.error("Task creation failed:", err);
    alert("CORE DISCONNECTED: Task could not be created.");
  }
}
