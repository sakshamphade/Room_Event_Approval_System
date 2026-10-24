/**
 * Room & Event Approval System - Frontend Application Logic
 * Implements Four-Member Sequential Approval Workflow:
 * Chairperson -> POC (Student Council) -> General Secretary -> College Authority
 * Communicates with Flask API at http://127.0.0.1:5000
 */

const API_BASE = "http://127.0.0.1:5000";

// Global Application State Store
const state = {
  committees: [],
  venues: [],
  events: [],
  bookings: [],
  approvals: [],
  pendingApprovals: [],
  approvalStats: {
    total_requests: 0,
    awaiting_my_approval: 0,
    approved_by_me: 0,
    rejected_by_me: 0,
    fully_approved: 0
  },
  auditTrail: [],
  currentUser: {
    user_id: 1,
    username: "booking_user",
    full_name: "Event Coordinator",
    email: "booking@college.edu",
    user_type: "BOOKING_USER",
    approval_role: null
  },
  activeBookingDetail: null, // Holds currently inspected booking with 4 stages
  currentView: "dashboard",
  isConnected: false,
  deleteTarget: null
};

const STAGES_LIST = [
  { order: 1, name: "Chairperson", roleName: "Chairperson" },
  { order: 2, name: "POC", roleName: "POC" },
  { order: 3, name: "General Secretary", roleName: "General Secretary" },
  { order: 4, name: "College Authority", roleName: "College Authority" }
];

// =============================================================================
// API Client & Communication Layer
// =============================================================================

async function apiRequest(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const defaultHeaders = {
    "Content-Type": "application/json",
    "Accept": "application/json"
  };

  // Attach X-User-Id header to enforce server-side identity on every request
  if (state.currentUser && state.currentUser.user_id) {
    defaultHeaders["X-User-Id"] = String(state.currentUser.user_id);
  }

  const config = {
    ...options,
    credentials: "include",
    headers: {
      ...defaultHeaders,
      ...(options.headers || {})
    }
  };

  if (config.body && typeof config.body === "object") {
    config.body = JSON.stringify(config.body);
  }

  try {
    const response = await fetch(url, config);
    let responseData = null;

    const contentType = response.headers.get("content-type");
    if (contentType && contentType.includes("application/json")) {
      responseData = await response.json();
    } else {
      const text = await response.text();
      try {
        responseData = JSON.parse(text);
      } catch {
        responseData = { message: text };
      }
    }

    if (!response.ok) {
      const errorMsg = (responseData && (responseData.error || responseData.message)) ||
        `Request failed with status ${response.status}`;
      throw new Error(errorMsg);
    }

    setApiStatus(true);
    return responseData;
  } catch (err) {
    if (err.name === "TypeError" && err.message.includes("fetch")) {
      setApiStatus(false);
      throw new Error("Could not connect to Flask backend at " + API_BASE);
    }
    throw err;
  }
}

function setApiStatus(isOnline) {
  state.isConnected = isOnline;
  const dot = document.getElementById("apiStatusDot");
  const text = document.getElementById("apiStatusText");
  const banner = document.getElementById("offlineBanner");

  if (dot && text) {
    if (isOnline) {
      dot.className = "status-indicator online";
      text.textContent = "API Connected";
    } else {
      dot.className = "status-indicator offline";
      text.textContent = "API Disconnected";
    }
  }

  if (banner) {
    banner.style.display = isOnline ? "none" : "flex";
  }
}

async function checkBackendHealth(showNotice = false) {
  try {
    const res = await fetch(`${API_BASE}/`);
    if (res.ok) {
      setApiStatus(true);
      if (showNotice) showToast("Connected", "Successfully connected to Flask API", "success");
      return true;
    }
  } catch {
    setApiStatus(false);
    if (showNotice) showToast("Connection Failed", "Unable to reach http://127.0.0.1:5000", "error");
    return false;
  }
}

// =============================================================================
// User Identity & Server-Side Role Switching
// =============================================================================

async function initCurrentUser() {
  try {
    const data = await apiRequest("/api/auth/me");
    if (data && data.user) {
      state.currentUser = data.user;
    }
    syncUserInterfaceRole();
  } catch (e) {
    console.warn("Could not fetch /api/auth/me, using default identity", e);
  }
}

async function handleUserRoleChange(selectedVal) {
  try {
    let payload = {};
    if (selectedVal === "booking_user") {
      payload = { username: "booking_user" };
    } else {
      payload = { approval_role: selectedVal };
    }

    const res = await apiRequest("/api/auth/switch-role", {
      method: "POST",
      body: payload
    });

    if (res && res.user) {
      state.currentUser = res.user;
      showToast("Identity Switched", `Active: ${res.user.full_name} (${res.user.approval_role || 'Booking Requester'})`, "success");
      syncUserInterfaceRole();
      await loadAllData();
      
      if (state.currentUser.user_type === "APPROVAL_USER") {
        navigateTo("approvals");
      } else {
        navigateTo("bookings");
      }
    }
  } catch (err) {
    showToast("Role Switch Failed", err.message, "error");
  }
}

function syncUserInterfaceRole() {
  const isApprovalUser = state.currentUser && state.currentUser.user_type === "APPROVAL_USER";
  const userRole = state.currentUser ? (state.currentUser.approval_role || "booking_user") : "booking_user";

  // Sync the topbar select dropdown value
  const selectEl = document.getElementById("activeUserRoleSelect");
  if (selectEl) {
    selectEl.value = userRole;
  }

  // Sidebar approvals nav item visibility
  const navApprovals = document.getElementById("navItemApprovals");
  if (navApprovals) {
    navApprovals.style.display = isApprovalUser ? "" : "none";
  }

  // Requester action buttons (e.g. New Booking button)
  const requesterActions = document.querySelectorAll(".requester-action");
  requesterActions.forEach(el => {
    el.style.display = isApprovalUser ? "none" : "";
  });

  // Topbar subtitle update
  const subtitle = document.getElementById("topbarSubtitle");
  if (subtitle) {
    if (isApprovalUser) {
      subtitle.textContent = `${state.currentUser.approval_role} Mode • Review and decide assigned approval stages`;
    } else {
      subtitle.textContent = "Booking User Mode • Submit & track room reservation requests";
    }
  }
}

// =============================================================================
// Data Loading & State Management
// =============================================================================

async function loadAllData(showSuccessToast = false) {
  const refreshIcon = document.getElementById("refreshIcon");
  if (refreshIcon) refreshIcon.style.animation = "spin 0.7s linear infinite";

  try {
    const isApprovalUser = state.currentUser && state.currentUser.user_type === "APPROVAL_USER";

    const fetchPromises = [
      apiRequest("/committees"),
      apiRequest("/venues"),
      apiRequest("/events"),
      apiRequest(isApprovalUser ? "/bookings" : "/bookings/my"),
      apiRequest("/approvals/audit-trail")
    ];

    if (isApprovalUser) {
      fetchPromises.push(apiRequest("/approvals/pending"));
      fetchPromises.push(apiRequest("/approvals/stats"));
    }

    const results = await Promise.all(fetchPromises);

    state.committees = Array.isArray(results[0]) ? results[0] : [];
    state.venues = Array.isArray(results[1]) ? results[1] : [];
    state.events = Array.isArray(results[2]) ? results[2] : [];
    state.bookings = Array.isArray(results[3]) ? results[3] : [];
    state.auditTrail = Array.isArray(results[4]) ? results[4] : [];

    if (isApprovalUser) {
      state.pendingApprovals = Array.isArray(results[5]) ? results[5] : [];
      state.approvalStats = results[6] || state.approvalStats;
    } else {
      state.pendingApprovals = [];
    }

    updateNavCounters();
    populateSelectDropdowns();
    renderCurrentView();

    if (showSuccessToast) {
      showToast("Data Synchronized", "Loaded fresh records from database", "success");
    }
  } catch (error) {
    console.error("Error loading application data:", error);
    setApiStatus(false);
    showToast("Backend Offline", error.message, "error");
  } finally {
    if (refreshIcon) refreshIcon.style.animation = "none";
  }
}

function updateNavCounters() {
  const isApprovalUser = state.currentUser && state.currentUser.user_type === "APPROVAL_USER";
  const pendingCount = isApprovalUser ? state.pendingApprovals.length : state.bookings.filter(b => b.status === "Pending").length;

  setText("navCounterCommittees", state.committees.length);
  setText("navCounterVenues", state.venues.length);
  setText("navCounterEvents", state.events.length);
  setText("navCounterBookings", state.bookings.length);
  setText("navCounterApprovals", state.pendingApprovals.length);

  // Dashboard Stat Cards
  setText("dashTotalCommittees", state.committees.length);
  setText("dashTotalVenues", state.venues.length);
  setText("dashTotalEvents", state.events.length);
  setText("dashPendingBookings", pendingCount);
  setText("dashApprovedBookings", state.bookings.filter(b => b.status === "Approved").length);
  setText("dashQuickPendingBadge", `${pendingCount} Pending`);
  setText("approvalsPendingCountBadge", `${state.pendingApprovals.length} Pending`);

  // Approver view summary cards
  if (isApprovalUser && state.approvalStats) {
    setText("approvalStatTotal", state.approvalStats.total_requests);
    setText("approvalStatAwaiting", state.approvalStats.awaiting_my_approval);
    setText("approvalStatApprovedByMe", state.approvalStats.approved_by_me);
    setText("approvalStatRejectedByMe", state.approvalStats.rejected_by_me);
    setText("approvalStatFullyApproved", state.approvalStats.fully_approved);
  }
}

function populateSelectDropdowns() {
  const eventCommitteeSelect = document.getElementById("eventCommitteeId");
  const filterEventCommittee = document.getElementById("filterEventCommittee");
  if (eventCommitteeSelect) {
    const curVal = eventCommitteeSelect.value;
    eventCommitteeSelect.innerHTML = '<option value="">-- Select Committee --</option>' +
      state.committees.map(c => `<option value="${c.committee_id}">${escapeHtml(c.name)}</option>`).join("");
    eventCommitteeSelect.value = curVal;
  }
  if (filterEventCommittee) {
    const curFilter = filterEventCommittee.value;
    filterEventCommittee.innerHTML = '<option value="">All Committees</option>' +
      state.committees.map(c => `<option value="${c.committee_id}">${escapeHtml(c.name)}</option>`).join("");
    filterEventCommittee.value = curFilter;
  }

  const bookingVenueSelect = document.getElementById("bookingVenueId");
  const filterBookingVenue = document.getElementById("filterBookingVenue");
  const filterVenueType = document.getElementById("filterVenueType");

  if (bookingVenueSelect) {
    const curVal = bookingVenueSelect.value;
    bookingVenueSelect.innerHTML = '<option value="">-- Select Venue --</option>' +
      state.venues.map(v => `<option value="${v.venue_id}">${escapeHtml(v.venue_name)} (Cap: ${v.capacity}, ${escapeHtml(v.location)})</option>`).join("");
    bookingVenueSelect.value = curVal;
  }
  if (filterBookingVenue) {
    const curVal = filterBookingVenue.value;
    filterBookingVenue.innerHTML = '<option value="">All Venues</option>' +
      state.venues.map(v => `<option value="${v.venue_id}">${escapeHtml(v.venue_name)}</option>`).join("");
    filterBookingVenue.value = curVal;
  }

  if (filterVenueType) {
    const types = [...new Set(state.venues.map(v => v.venue_type).filter(Boolean))];
    const curType = filterVenueType.value;
    filterVenueType.innerHTML = '<option value="">All Venue Types</option>' +
      types.map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join("");
    filterVenueType.value = curType;
  }

  const bookingEventSelect = document.getElementById("bookingEventId");
  if (bookingEventSelect) {
    const curVal = bookingEventSelect.value;
    bookingEventSelect.innerHTML = '<option value="">-- Select Event --</option>' +
      state.events.map(e => `<option value="${e.event_id}">${escapeHtml(e.event_name)} (${formatDate(e.event_date)})</option>`).join("");
    bookingEventSelect.value = curVal;
  }
}

// =============================================================================
// Navigation & Views
// =============================================================================

const viewMetadata = {
  dashboard: { title: "Dashboard", subtitle: "Overview, quick metrics & system analytics" },
  committees: { title: "Committees", subtitle: "Manage organizing committees and faculty advisors" },
  venues: { title: "Venues", subtitle: "Manage campus rooms, halls, capacities and locations" },
  events: { title: "Events", subtitle: "Manage scheduled college events and programs" },
  bookings: { title: "Booking Requests", subtitle: "Manage room reservation requests and slot bookings" },
  approvals: { title: "Approvals", subtitle: "Review pending venue requests and inspect audit logs" }
};

function handlePendingStatCardClick() {
  if (state.currentUser && state.currentUser.user_type === "APPROVAL_USER") {
    navigateTo("approvals");
  } else {
    navigateTo("bookings");
  }
}

function navigateTo(viewName) {
  const isApprovalUser = state.currentUser && state.currentUser.user_type === "APPROVAL_USER";
  if (viewName === "approvals" && !isApprovalUser) {
    viewName = "bookings";
  }

  state.currentView = viewName;

  document.querySelectorAll(".sidebar-nav .nav-item").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-view") === viewName);
  });

  document.querySelectorAll(".view-section").forEach(sec => {
    sec.classList.toggle("active", sec.id === `view-${viewName}`);
  });

  const meta = viewMetadata[viewName] || { title: "Dashboard", subtitle: "" };
  setText("topbarTitle", meta.title);

  syncUserInterfaceRole();
  toggleMobileSidebar(false);
  renderCurrentView();
}

function renderCurrentView() {
  switch (state.currentView) {
    case "dashboard":
      renderDashboard();
      break;
    case "committees":
      renderCommitteesTable();
      break;
    case "venues":
      renderVenuesTable();
      break;
    case "events":
      renderEventsTable();
      break;
    case "bookings":
      renderBookingsTable();
      break;
    case "approvals":
      renderApprovalsView();
      break;
  }
}

function toggleMobileSidebar(open) {
  const sidebar = document.getElementById("appSidebar");
  const backdrop = document.getElementById("sidebarBackdrop");
  if (sidebar && backdrop) {
    if (open) {
      sidebar.classList.add("mobile-open");
      backdrop.classList.add("show");
    } else {
      sidebar.classList.remove("mobile-open");
      backdrop.classList.remove("show");
    }
  }
}

// =============================================================================
// Stepper Generation Helpers
// =============================================================================

function renderWorkflowStepperHtml(currentStage, status, stages = []) {
  return STAGES_LIST.map((stepDef) => {
    const stageData = stages.find(s => s.stage_order === stepDef.order);
    let stateClass = "step-waiting";
    let iconSvg = `<span>${stepDef.order}</span>`;
    let subtext = "Awaiting";

    if (stageData) {
      if (stageData.status === "Approved") {
        stateClass = "step-approved";
        iconSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
        subtext = stageData.approver_name ? escapeHtml(stageData.approver_name.split(" ")[0]) : "Approved";
      } else if (stageData.status === "Rejected") {
        stateClass = "step-rejected";
        iconSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
        subtext = "Rejected";
      } else if (status === "Pending" && currentStage === stepDef.order) {
        stateClass = "step-current";
        subtext = "Pending Decision";
      }
    } else {
      if (status === "Approved") {
        stateClass = "step-approved";
        subtext = "Approved";
      } else if (status === "Rejected") {
        stateClass = "step-rejected";
        subtext = "Rejected";
      } else if (currentStage === stepDef.order) {
        stateClass = "step-current";
        subtext = "Pending Decision";
      }
    }

    return `
      <div class="step-item ${stateClass}">
        <div class="step-bubble">${iconSvg}</div>
        <div class="step-title">${escapeHtml(stepDef.name)}</div>
        <div class="step-subtext">${subtext}</div>
      </div>
    `;
  }).join("");
}

function renderCompactTableStepperHtml(currentStage, status) {
  return STAGES_LIST.map((stepDef, idx) => {
    let pillClass = "waiting";
    let label = stepDef.name.split(" ")[0];

    if (status === "Approved") {
      pillClass = "approved";
    } else if (status === "Rejected") {
      pillClass = (currentStage === stepDef.order) ? "rejected" : (currentStage > stepDef.order ? "approved" : "waiting");
    } else {
      if (stepDef.order < currentStage) pillClass = "approved";
      else if (stepDef.order === currentStage) pillClass = "current";
      else pillClass = "waiting";
    }

    const arrow = (idx < STAGES_LIST.length - 1) ? `<span class="table-step-arrow">&rarr;</span>` : "";

    return `
      <span class="table-step-pill ${pillClass}">${label}</span>${arrow}
    `;
  }).join("");
}

// =============================================================================
// View Renderers
// =============================================================================

function renderDashboard() {
  const tableBody = document.getElementById("dashRecentBookingsTable");
  if (!tableBody) return;

  const isApprovalUser = state.currentUser && state.currentUser.user_type === "APPROVAL_USER";
  const recent = [...state.bookings].sort((a, b) => b.request_id - a.request_id).slice(0, 6);

  if (recent.length === 0) {
    tableBody.innerHTML = `
      <tr>
        <td colspan="6" class="table-empty-state">
          <h4>No Booking Requests</h4>
          <p>Create a new booking request to get started.</p>
        </td>
      </tr>
    `;
  } else {
    tableBody.innerHTML = recent.map(b => {
      const event = state.events.find(e => e.event_id === b.event_id);
      const venue = state.venues.find(v => v.venue_id === b.venue_id);
      const eventName = event ? event.event_name : `Event #${b.event_id}`;
      const venueName = venue ? venue.venue_name : `Venue #${b.venue_id}`;

      return `
        <tr>
          <td><strong>#${b.request_id}</strong></td>
          <td><strong>${escapeHtml(eventName)}</strong></td>
          <td>${escapeHtml(venueName)}</td>
          <td>${formatDateTime(b.start_time)}</td>
          <td>${renderStatusBadge(b.status)}</td>
          <td>
            ${isApprovalUser ? `
              <button class="btn btn-sm btn-primary" onclick="openApprovalReviewModal(${b.request_id})">
                Review &amp; Decide
              </button>
            ` : `
              <button class="btn btn-sm btn-secondary" onclick="openApprovalReviewModal(${b.request_id})">
                Track Progress
              </button>
            `}
          </td>
        </tr>
      `;
    }).join("");
  }

  const venueSummaryBox = document.getElementById("dashVenueSummary");
  if (venueSummaryBox) {
    const totalCap = state.venues.reduce((acc, v) => acc + (parseInt(v.capacity) || 0), 0);
    const maxVenue = state.venues.reduce((prev, curr) => (curr.capacity > (prev?.capacity || 0)) ? curr : prev, null);

    venueSummaryBox.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 12px; font-size: 0.85rem;">
        <div style="display: flex; justify-content: space-between; border-bottom: 1px solid var(--border-color); padding-bottom: 8px;">
          <span style="color: var(--text-muted);">Total Campus Venues:</span>
          <strong>${state.venues.length} spaces</strong>
        </div>
        <div style="display: flex; justify-content: space-between; border-bottom: 1px solid var(--border-color); padding-bottom: 8px;">
          <span style="color: var(--text-muted);">Total Seating Capacity:</span>
          <strong>${totalCap.toLocaleString()} seats</strong>
        </div>
        <div style="display: flex; justify-content: space-between; border-bottom: 1px solid var(--border-color); padding-bottom: 8px;">
          <span style="color: var(--text-muted);">Largest Venue:</span>
          <strong>${maxVenue ? `${escapeHtml(maxVenue.venue_name)} (${maxVenue.capacity})` : 'N/A'}</strong>
        </div>
        <div style="display: flex; justify-content: space-between;">
          <span style="color: var(--text-muted);">Active Bookings:</span>
          <strong>${state.bookings.filter(b => b.status === 'Approved').length} approved</strong>
        </div>
      </div>
    `;
  }
}

function renderCommitteesTable() {
  const tableBody = document.getElementById("committeesTableBody");
  const search = (document.getElementById("searchCommittees")?.value || "").toLowerCase().trim();
  if (!tableBody) return;

  const filtered = state.committees.filter(c => {
    return !search ||
      c.name.toLowerCase().includes(search) ||
      c.advisor.toLowerCase().includes(search) ||
      c.contact_email.toLowerCase().includes(search);
  });

  if (filtered.length === 0) {
    tableBody.innerHTML = `
      <tr>
        <td colspan="6" class="table-empty-state">
          <h4>No Committees Found</h4>
          <p>${search ? 'No committees match your search.' : 'Add your first committee using the button above.'}</p>
        </td>
      </tr>
    `;
    return;
  }

  tableBody.innerHTML = filtered.map(c => {
    const linkedEvents = state.events.filter(e => e.committee_id === c.committee_id);
    return `
      <tr>
        <td><strong>#${c.committee_id}</strong></td>
        <td>
          <div style="font-weight: 600; color: var(--text-main);">${escapeHtml(c.name)}</div>
        </td>
        <td>${escapeHtml(c.advisor)}</td>
        <td>
          <a href="mailto:${escapeHtml(c.contact_email)}" style="color: var(--primary); text-decoration: underline;">
            ${escapeHtml(c.contact_email)}
          </a>
        </td>
        <td>
          <span class="badge badge-info">${linkedEvents.length} Event${linkedEvents.length === 1 ? '' : 's'}</span>
        </td>
        <td style="text-align: right;">
          <div class="table-row-actions" style="justify-content: flex-end;">
            <button class="btn btn-sm btn-secondary" onclick="openCommitteeModal(${c.committee_id})" title="Edit Committee">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
              </svg>
              <span>Edit</span>
            </button>
            <button class="btn btn-sm btn-danger-outline" onclick="confirmDelete('committee', ${c.committee_id}, '${escapeQuote(c.name)}')" title="Delete Committee">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              </svg>
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function renderVenuesTable() {
  const tableBody = document.getElementById("venuesTableBody");
  const search = (document.getElementById("searchVenues")?.value || "").toLowerCase().trim();
  const typeFilter = document.getElementById("filterVenueType")?.value || "";
  if (!tableBody) return;

  const filtered = state.venues.filter(v => {
    const matchesSearch = !search ||
      v.venue_name.toLowerCase().includes(search) ||
      (v.venue_type && v.venue_type.toLowerCase().includes(search)) ||
      (v.location && v.location.toLowerCase().includes(search));
    const matchesType = !typeFilter || v.venue_type === typeFilter;
    return matchesSearch && matchesType;
  });

  if (filtered.length === 0) {
    tableBody.innerHTML = `
      <tr>
        <td colspan="6" class="table-empty-state">
          <h4>No Venues Found</h4>
          <p>${search || typeFilter ? 'No venues match your criteria.' : 'Add your first venue using the button above.'}</p>
        </td>
      </tr>
    `;
    return;
  }

  tableBody.innerHTML = filtered.map(v => {
    return `
      <tr>
        <td><strong>#${v.venue_id}</strong></td>
        <td>
          <div style="font-weight: 600; color: var(--text-main);">${escapeHtml(v.venue_name)}</div>
        </td>
        <td><span class="badge badge-neutral">${escapeHtml(v.venue_type || 'General')}</span></td>
        <td>${escapeHtml(v.location || 'Campus')}</td>
        <td>
          <span class="badge badge-info" style="font-weight: 600;">
            ${v.capacity} Seats
          </span>
        </td>
        <td style="text-align: right;">
          <div class="table-row-actions" style="justify-content: flex-end;">
            <button class="btn btn-sm btn-secondary" onclick="openVenueModal(${v.venue_id})" title="Edit Venue">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
              </svg>
              <span>Edit</span>
            </button>
            <button class="btn btn-sm btn-danger-outline" onclick="confirmDelete('venue', ${v.venue_id}, '${escapeQuote(v.venue_name)}')" title="Delete Venue">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              </svg>
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function renderEventsTable() {
  const tableBody = document.getElementById("eventsTableBody");
  const search = (document.getElementById("searchEvents")?.value || "").toLowerCase().trim();
  const commFilter = document.getElementById("filterEventCommittee")?.value || "";
  if (!tableBody) return;

  const filtered = state.events.filter(e => {
    const matchesSearch = !search || e.event_name.toLowerCase().includes(search);
    const matchesComm = !commFilter || String(e.committee_id) === String(commFilter);
    return matchesSearch && matchesComm;
  });

  if (filtered.length === 0) {
    tableBody.innerHTML = `
      <tr>
        <td colspan="6" class="table-empty-state">
          <h4>No Events Found</h4>
          <p>${search || commFilter ? 'No events match your filter criteria.' : 'Create an event using the button above.'}</p>
        </td>
      </tr>
    `;
    return;
  }

  tableBody.innerHTML = filtered.map(e => {
    const comm = state.committees.find(c => c.committee_id === e.committee_id);
    const commName = comm ? comm.name : `Committee #${e.committee_id}`;

    return `
      <tr>
        <td><strong>#${e.event_id}</strong></td>
        <td>
          <div style="font-weight: 600; color: var(--text-main);">${escapeHtml(e.event_name)}</div>
        </td>
        <td>${formatDate(e.event_date)}</td>
        <td>
          <span class="badge badge-neutral">${e.expected_attendees} Expected</span>
        </td>
        <td>
          <span style="font-weight: 500; color: var(--primary);">${escapeHtml(commName)}</span>
        </td>
        <td style="text-align: right;">
          <div class="table-row-actions" style="justify-content: flex-end;">
            <button class="btn btn-sm btn-outline-primary" onclick="openBookingModal(null, ${e.event_id})" title="Book Venue for this Event">
              <span>Book</span>
            </button>
            <button class="btn btn-sm btn-secondary" onclick="openEventModal(${e.event_id})" title="Edit Event">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
              </svg>
            </button>
            <button class="btn btn-sm btn-danger-outline" onclick="confirmDelete('event', ${e.event_id}, '${escapeQuote(e.event_name)}')" title="Delete Event">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              </svg>
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function renderBookingsTable() {
  const tableBody = document.getElementById("bookingsTableBody");
  const search = (document.getElementById("searchBookings")?.value || "").toLowerCase().trim();
  const statusFilter = document.getElementById("filterBookingStatus")?.value || "";
  const venueFilter = document.getElementById("filterBookingVenue")?.value || "";
  if (!tableBody) return;

  const isApprovalUser = state.currentUser && state.currentUser.user_type === "APPROVAL_USER";

  const filtered = state.bookings.filter(b => {
    const event = state.events.find(e => e.event_id === b.event_id);
    const venue = state.venues.find(v => v.venue_id === b.venue_id);
    const eventName = event ? event.event_name.toLowerCase() : "";
    const venueName = venue ? venue.venue_name.toLowerCase() : "";

    const matchesSearch = !search ||
      String(b.request_id).includes(search) ||
      eventName.includes(search) ||
      venueName.includes(search);

    const matchesStatus = !statusFilter || b.status === statusFilter;
    const matchesVenue = !venueFilter || String(b.venue_id) === String(venueFilter);

    return matchesSearch && matchesStatus && matchesVenue;
  });

  if (filtered.length === 0) {
    tableBody.innerHTML = `
      <tr>
        <td colspan="7" class="table-empty-state">
          <h4>No Bookings Found</h4>
          <p>${search || statusFilter || venueFilter ? 'No booking requests match your filters.' : 'No bookings in the database.'}</p>
        </td>
      </tr>
    `;
    return;
  }

  tableBody.innerHTML = filtered.map(b => {
    const event = state.events.find(e => e.event_id === b.event_id);
    const venue = state.venues.find(v => v.venue_id === b.venue_id);
    const eventName = event ? event.event_name : `Event #${b.event_id}`;
    const venueName = venue ? `${venue.venue_name} (${venue.location})` : `Venue #${b.venue_id}`;

    return `
      <tr>
        <td><strong>#${b.request_id}</strong></td>
        <td>
          <div style="font-weight: 600; color: var(--text-main);">${escapeHtml(eventName)}</div>
          <div style="margin-top: 4px;">
            <div class="table-stepper">${renderCompactTableStepperHtml(b.current_stage, b.status)}</div>
          </div>
        </td>
        <td>${escapeHtml(venueName)}</td>
        <td>${formatDateTime(b.start_time)}</td>
        <td>${formatDateTime(b.end_time)}</td>
        <td>${renderStatusBadge(b.status)}</td>
        <td style="text-align: right;">
          <div class="table-row-actions" style="justify-content: flex-end;">
            <button class="btn btn-sm ${isApprovalUser ? 'btn-primary' : 'btn-outline-primary'}" onclick="openApprovalReviewModal(${b.request_id})" title="${isApprovalUser ? 'Review & Decide' : 'Track Approval Workflow'}">
              <span>${isApprovalUser ? 'Review &amp; Decide' : 'Track Status'}</span>
            </button>
            ${!isApprovalUser ? `
              <button class="btn btn-sm btn-secondary" onclick="openBookingModal(${b.request_id})" title="Edit Booking">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                </svg>
              </button>
              <button class="btn btn-sm btn-danger-outline" onclick="confirmDelete('booking', ${b.request_id}, 'Booking Request #${b.request_id}')" title="Delete Booking">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                </svg>
              </button>
            ` : ''}
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function renderApprovalsView() {
  renderPendingApprovalsTable();
  renderApprovalsTable();
}

function renderPendingApprovalsTable() {
  const tableBody = document.getElementById("pendingApprovalsTableBody");
  if (!tableBody) return;

  if (state.pendingApprovals.length === 0) {
    tableBody.innerHTML = `
      <tr>
        <td colspan="7" class="table-empty-state">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: #10b981;">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
            <polyline points="22 4 12 14.01 9 11.01"></polyline>
          </svg>
          <h4>Queue Clear!</h4>
          <p>No booking requests are currently awaiting approval at your authority stage.</p>
        </td>
      </tr>
    `;
    return;
  }

  tableBody.innerHTML = state.pendingApprovals.map(b => {
    return `
      <tr>
        <td><strong>#${b.request_id}</strong></td>
        <td>
          <div style="font-weight: 600; color: var(--text-main);">${escapeHtml(b.event_name)}</div>
          <div style="font-size: 0.78rem; color: var(--text-muted);">${escapeHtml(b.committee_name || 'Committee')}</div>
        </td>
        <td>
          <div>${escapeHtml(b.venue_name)}</div>
          <div style="font-size: 0.75rem; color: var(--text-muted);">${b.location} (Cap: ${b.capacity})</div>
        </td>
        <td>
          <div>${formatDate(b.event_date)}</div>
          <div style="font-size: 0.75rem; color: var(--text-muted);">${formatDateTime(b.start_time)} &ndash; ${formatDateTime(b.end_time)}</div>
        </td>
        <td>
          <span class="badge badge-neutral">${b.expected_attendees} Expected</span>
        </td>
        <td>
          <span class="badge badge-pending" style="font-weight: 700;">Stage ${b.current_stage}: ${escapeHtml(b.current_stage_name)}</span>
        </td>
        <td style="text-align: right;">
          <button class="btn btn-sm btn-primary" onclick="openApprovalReviewModal(${b.request_id})" title="Review Details &amp; Decide">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 13px; height: 13px;">
              <path d="m9 12 2 2 4-4"></path>
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
            </svg>
            <span>Review &amp; Decide</span>
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

function renderApprovalsTable() {
  const tableBody = document.getElementById("approvalsTableBody");
  const search = (document.getElementById("searchApprovals")?.value || "").toLowerCase().trim();
  const decisionFilter = document.getElementById("filterApprovalDecision")?.value || "";
  if (!tableBody) return;

  const filtered = state.auditTrail.filter(a => {
    const matchesSearch = !search ||
      String(a.request_id).includes(search) ||
      (a.approver_role && a.approver_role.toLowerCase().includes(search)) ||
      (a.remarks && a.remarks.toLowerCase().includes(search)) ||
      (a.decided_by_name && a.decided_by_name.toLowerCase().includes(search));

    const matchesDecision = !decisionFilter || a.decision === decisionFilter;
    return matchesSearch && matchesDecision;
  });

  if (filtered.length === 0) {
    tableBody.innerHTML = `
      <tr>
        <td colspan="7" class="table-empty-state">
          <h4>No Audit Records</h4>
          <p>${search || decisionFilter ? 'No records match your filters.' : 'No approval audit records logged yet.'}</p>
        </td>
      </tr>
    `;
    return;
  }

  tableBody.innerHTML = filtered.map(a => {
    return `
      <tr>
        <td><strong>#${a.audit_id}</strong></td>
        <td>
          <div style="font-weight: 600; color: var(--text-main);">Req #${a.request_id}</div>
          <div style="font-size: 0.75rem; color: var(--text-muted);">${escapeHtml(a.approver_role)}</div>
        </td>
        <td>${escapeHtml(a.decided_by_name || 'System Approver')}</td>
        <td>${renderStatusBadge(a.decision)}</td>
        <td>
          <div style="font-size: 0.85rem; max-width: 280px; word-break: break-word;">
            ${escapeHtml(a.remarks || 'No remarks')}
          </div>
        </td>
        <td>${formatDateTime(a.decided_at)}</td>
        <td style="text-align: right;">
          <button class="btn btn-sm btn-secondary" onclick="openApprovalReviewModal(${a.request_id})" title="Inspect Workflow">
            <span>View Flow</span>
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

// =============================================================================
// Review & Decision Modal Logic
// =============================================================================

async function openApprovalReviewModal(requestId) {
  try {
    const data = await apiRequest(`/approvals/booking/${requestId}/progress`);
    if (!data || !data.booking) {
      showToast("Error", "Could not load booking details", "error");
      return;
    }

    state.activeBookingDetail = data;
    const b = data.booking;
    const stages = data.stages || [];

    document.getElementById("approvalRequestId").value = b.request_id;
    document.getElementById("approvalModalTitle").textContent = `Booking Request #${b.request_id} Review`;

    // Populate request summary card
    setText("approvalSummaryEvent", b.event_name || `Event #${b.event_id}`);
    setText("approvalSummaryVenue", `Venue: ${b.venue_name} (Capacity: ${b.capacity})`);
    setText("approvalSummaryTime", `Window: ${formatDateTime(b.start_time)} to ${formatDateTime(b.end_time)}`);
    
    const reqBox = document.getElementById("approvalSummaryRequester");
    if (reqBox) {
      reqBox.innerHTML = `
        <div>Requester: <strong>${escapeHtml(b.requester_name || 'Event Coordinator')}</strong></div>
        <div class="badge ${b.status === 'Approved' ? 'badge-approved' : (b.status === 'Rejected' ? 'badge-rejected' : 'badge-pending')}" style="margin-top: 4px;">
          ${b.status}
        </div>
      `;
    }

    // Render 4-Stage Stepper inside modal
    const stepperContainer = document.getElementById("approvalModalStepper");
    if (stepperContainer) {
      stepperContainer.innerHTML = renderWorkflowStepperHtml(b.current_stage, b.status, stages);
    }

    // Render Previous Approvers Remarks
    const historyList = document.getElementById("approvalHistoryList");
    const decidedStages = stages.filter(s => s.status !== "Pending");

    if (historyList) {
      if (decidedStages.length === 0) {
        historyList.innerHTML = `<div style="color: #64748b; font-style: italic;">No approval decisions recorded yet. Initial stage is pending Chairperson evaluation.</div>`;
      } else {
        historyList.innerHTML = decidedStages.map(s => `
          <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px;">
              <span style="font-weight: 700; color: #1e293b;">${s.stage_order}. ${escapeHtml(s.stage_name)}</span>
              <span class="badge ${s.status === 'Approved' ? 'badge-approved' : 'badge-rejected'}">${s.status}</span>
            </div>
            <div style="color: #475569; font-size: 0.8rem;">
              "${escapeHtml(s.remarks || 'No remarks provided')}"
            </div>
            <div style="font-size: 0.7rem; color: #94a3b8; margin-top: 3px;">
              Decided by: ${escapeHtml(s.approver_name || s.stage_name)} &bull; ${formatDateTime(s.decided_at)}
            </div>
          </div>
        `).join("");
      }
    }

    // Check if current user is authorized to submit a decision at this stage
    const isApprovalUser = state.currentUser && state.currentUser.user_type === "APPROVAL_USER";
    const userRole = state.currentUser ? state.currentUser.approval_role : null;
    const stageOrderMap = { "Chairperson": 1, "POC": 2, "General Secretary": 3, "College Authority": 4 };
    const userStageOrder = stageOrderMap[userRole];

    const decisionSection = document.getElementById("approvalDecisionSection");
    const readOnlyNotice = document.getElementById("approvalReadOnlyNotice");
    const readOnlyText = document.getElementById("approvalReadOnlyText");
    const submitBtn = document.getElementById("approvalSubmitBtn");

    let isEligible = false;
    let restrictionReason = "";

    if (!isApprovalUser) {
      restrictionReason = "You are logged in as a Booking User. You can track progress and remarks in read-only mode.";
    } else if (b.status === "Approved") {
      restrictionReason = "This booking request is already fully approved by all four authorities.";
    } else if (b.status === "Rejected") {
      restrictionReason = `This booking request was rejected at Stage ${b.rejected_by_stage || ''} and the workflow is terminated.`;
    } else if (b.current_stage !== userStageOrder) {
      if (b.current_stage < userStageOrder) {
        restrictionReason = `Awaiting prior stages. Stage ${STAGES_LIST.find(s=>s.order===b.current_stage)?.name} must decide before ${userRole} can act.`;
      } else {
        restrictionReason = `Stage ${userRole} has already been completed for this booking.`;
      }
    } else if (b.requester_id === state.currentUser.user_id) {
      restrictionReason = "Requesters cannot review or decide their own booking requests.";
    } else {
      isEligible = true;
    }

    if (isEligible) {
      if (decisionSection) decisionSection.style.display = "block";
      if (readOnlyNotice) readOnlyNotice.style.display = "none";
      if (submitBtn) submitBtn.style.display = "inline-flex";
      document.getElementById("approvalRemarks").value = "";
      toggleRejectionRequirement(false);
    } else {
      if (decisionSection) decisionSection.style.display = "none";
      if (readOnlyNotice) {
        readOnlyNotice.style.display = "block";
        if (readOnlyText) readOnlyText.textContent = restrictionReason;
      }
      if (submitBtn) submitBtn.style.display = "none";
    }

    openModal("approvalModal");
  } catch (err) {
    showToast("Error", err.message, "error");
  }
}

function toggleRejectionRequirement(isRejection) {
  const remarksLabel = document.getElementById("approvalRemarksLabel");
  const remarksHint = document.getElementById("approvalRemarksHint");
  const remarksInput = document.getElementById("approvalRemarks");

  if (isRejection) {
    if (remarksLabel) remarksLabel.innerHTML = 'Rejection Reason <span class="required" style="color: #dc2626;">* (Required)</span>';
    if (remarksHint) remarksHint.textContent = "Please provide an explicit, meaningful reason for declining this request.";
    if (remarksInput) remarksInput.required = true;
  } else {
    if (remarksLabel) remarksLabel.innerHTML = 'Approval Remarks / Notes (Optional)';
    if (remarksHint) remarksHint.textContent = "Remarks will be recorded in the official audit trail.";
    if (remarksInput) remarksInput.required = false;
  }
}

async function handleApprovalSubmit(e) {
  e.preventDefault();

  const isApprovalUser = state.currentUser && state.currentUser.user_type === "APPROVAL_USER";
  if (!isApprovalUser) {
    showToast("Restricted", "Booking users cannot access approval decision endpoints.", "error");
    closeModal("approvalModal");
    return;
  }

  const requestId = parseInt(document.getElementById("approvalRequestId").value, 10);
  const radios = document.getElementsByName("approvalDecision");
  let decision = "Approved";
  radios.forEach(r => {
    if (r.checked) decision = r.value;
  });

  const remarks = document.getElementById("approvalRemarks").value.trim();

  if (decision === "Rejected" && !remarks) {
    showToast("Reason Required", "A meaningful rejection reason is required before rejecting a request.", "warning");
    document.getElementById("approvalRemarks").focus();
    return;
  }

  // Confirmation prompt before submitting
  const confirmMsg = decision === "Approved"
    ? `Are you sure you want to approve Stage (${state.currentUser.approval_role}) for Booking #${requestId}?`
    : `Are you sure you want to REJECT Booking #${requestId}? This will terminate the approval workflow.`;

  if (!confirm(confirmMsg)) {
    return;
  }

  const submitBtn = document.getElementById("approvalSubmitBtn");
  submitBtn.disabled = true;

  try {
    const res = await apiRequest("/approvals/decide", {
      method: "POST",
      body: {
        request_id: requestId,
        decision,
        remarks
      }
    });

    showToast("Decision Recorded", res.message || `Recorded ${decision}`, "success");
    closeModal("approvalModal");
    await loadAllData();
  } catch (err) {
    showToast("Decision Failed", err.message, "error");
  } finally {
    submitBtn.disabled = false;
  }
}

// =============================================================================
// Form Handlers (Committees, Venues, Events, Bookings)
// =============================================================================

/* ------------------------------------------------------------------
 * Modal open/close helpers
 * The page's real scroll container is .app-main (a flex child that
 * grows beyond the viewport).  We freeze it — not <body> — when any
 * modal is open, and restore it when the last modal closes.
 * ------------------------------------------------------------------ */
function _getScrollContainer() {
  return document.querySelector(".app-main") || document.body;
}

function _freezeScroll() {
  const el = _getScrollContainer();
  if (!el._savedOverflow) el._savedOverflow = el.style.overflow || "";
  el.style.overflow = "hidden";
  document.body.classList.add("modal-open"); // keeps the CSS rule active too
}

function _thawScroll() {
  // Only thaw when every modal is fully closed
  if (document.querySelector(".modal-backdrop.show")) return;
  const el = _getScrollContainer();
  el.style.overflow = el._savedOverflow || "";
  el._savedOverflow = "";
  document.body.classList.remove("modal-open");
}

function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  modal.classList.add("show");
  _freezeScroll();
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return;
  modal.classList.remove("show");
  _thawScroll();
}

// Close when clicking the dim backdrop area (outside the modal window)
document.addEventListener("click", e => {
  if (e.target.classList.contains("modal-backdrop")) {
    e.target.classList.remove("show");
    _thawScroll();
  }
});

/**
 * Wheel-event containment.
 * Attached once at DOMContentLoaded to every .modal-body.
 *
 * Strategy — three layers working together:
 *  1. CSS  overscroll-behavior:contain  (already on .modal-body) handles
 *     Chrome/Edge natively without any JS.
 *  2. stopPropagation() ensures the event never bubbles past the modal-body
 *     to .app-main even in older browsers / edge-cases.
 *  3. preventDefault() only at scroll boundaries prevents the rubber-band
 *     "pull-to-refresh" or page scroll on Safari/Firefox.
 *
 * Textareas: the listener target-checks — if the event originated inside a
 * textarea or an element with its own scroll, we let it pass through.
 */
function attachModalWheelContainment() {
  document.querySelectorAll(".modal-body").forEach(bodyEl => {
    bodyEl.addEventListener("wheel", function (e) {
      // If the originating element is a textarea, let it handle its own scroll
      let target = e.target;
      while (target && target !== bodyEl) {
        const style = window.getComputedStyle(target);
        const overflowY = style.overflowY;
        const canScroll = overflowY === "auto" || overflowY === "scroll";
        if (canScroll && target.scrollHeight > target.clientHeight) {
          return; // let the inner element scroll naturally
        }
        target = target.parentElement;
      }

      // Stop propagation — event must not reach .app-main
      e.stopPropagation();

      const atTop    = bodyEl.scrollTop <= 0;
      const atBottom = bodyEl.scrollTop + bodyEl.clientHeight >= bodyEl.scrollHeight - 1;

      // Prevent default only at boundaries (stops pull-to-refresh / page bounce)
      if ((atTop && e.deltaY < 0) || (atBottom && e.deltaY > 0)) {
        e.preventDefault();
      }
    }, { passive: false });
  });
}

/* ---------- Committee Modals ---------- */
function openNewCommitteeModal() {
  openCommitteeModal();
}

function openCommitteeModal(id = null) {
  const form = document.getElementById("committeeForm");
  const title = document.getElementById("committeeModalTitle");
  form.reset();
  document.getElementById("committeeFormId").value = "";

  if (id) {
    const committee = state.committees.find(c => c.committee_id === id);
    if (!committee) return;
    title.textContent = "Edit Committee";
    document.getElementById("committeeFormId").value = committee.committee_id;
    document.getElementById("committeeName").value = committee.name;
    document.getElementById("committeeAdvisor").value = committee.advisor;
    document.getElementById("committeeEmail").value = committee.contact_email;
  } else {
    title.textContent = "Add Committee";
  }

  openModal("committeeModal");
}

async function handleCommitteeSubmit(e) {
  e.preventDefault();
  const id = document.getElementById("committeeFormId").value;
  const submitBtn = document.getElementById("committeeSubmitBtn");
  submitBtn.disabled = true;

  const payload = {
    name: document.getElementById("committeeName").value.trim(),
    advisor: document.getElementById("committeeAdvisor").value.trim(),
    contact_email: document.getElementById("committeeEmail").value.trim()
  };

  try {
    if (id) {
      await apiRequest(`/committees/${id}`, { method: "PUT", body: payload });
      showToast("Updated", "Committee details updated successfully", "success");
    } else {
      await apiRequest("/committees", { method: "POST", body: payload });
      showToast("Created", "New committee registered successfully", "success");
    }
    closeModal("committeeModal");
    await loadAllData();
  } catch (err) {
    showToast("Error", err.message, "error");
  } finally {
    submitBtn.disabled = false;
  }
}

/* ---------- Venue Modals ---------- */
function openNewVenueModal() {
  openVenueModal();
}

function openVenueModal(id = null) {
  const form = document.getElementById("venueForm");
  const title = document.getElementById("venueModalTitle");
  form.reset();
  document.getElementById("venueFormId").value = "";

  if (id) {
    const venue = state.venues.find(v => v.venue_id === id);
    if (!venue) return;
    title.textContent = "Edit Venue";
    document.getElementById("venueFormId").value = venue.venue_id;
    document.getElementById("venueName").value = venue.venue_name;
    document.getElementById("venueType").value = venue.venue_type;
    document.getElementById("venueCapacity").value = venue.capacity;
    document.getElementById("venueLocation").value = venue.location;
  } else {
    title.textContent = "Add Venue";
  }

  openModal("venueModal");
}

async function handleVenueSubmit(e) {
  e.preventDefault();
  const id = document.getElementById("venueFormId").value;
  const submitBtn = document.getElementById("venueSubmitBtn");
  submitBtn.disabled = true;

  const payload = {
    venue_name: document.getElementById("venueName").value.trim(),
    venue_type: document.getElementById("venueType").value.trim(),
    capacity: parseInt(document.getElementById("venueCapacity").value, 10),
    location: document.getElementById("venueLocation").value.trim()
  };

  try {
    if (id) {
      await apiRequest(`/venues/${id}`, { method: "PUT", body: payload });
      showToast("Updated", "Venue details updated successfully", "success");
    } else {
      await apiRequest("/venues", { method: "POST", body: payload });
      showToast("Created", "New venue added successfully", "success");
    }
    closeModal("venueModal");
    await loadAllData();
  } catch (err) {
    showToast("Error", err.message, "error");
  } finally {
    submitBtn.disabled = false;
  }
}

/* ---------- Event Modals ---------- */
function openNewEventModal() {
  openEventModal();
}

function openEventModal(id = null) {
  const form = document.getElementById("eventForm");
  const title = document.getElementById("eventModalTitle");
  form.reset();
  document.getElementById("eventFormId").value = "";

  populateSelectDropdowns();

  if (id) {
    const event = state.events.find(e => e.event_id === id);
    if (!event) return;
    title.textContent = "Edit Event";
    document.getElementById("eventFormId").value = event.event_id;
    document.getElementById("eventName").value = event.event_name;
    document.getElementById("eventCommitteeId").value = event.committee_id;
    document.getElementById("eventDate").value = toDateInput(event.event_date);
    document.getElementById("eventAttendees").value = event.expected_attendees;
  } else {
    title.textContent = "Add Event";
  }

  openModal("eventModal");
}

async function handleEventSubmit(e) {
  e.preventDefault();
  const id = document.getElementById("eventFormId").value;
  const submitBtn = document.getElementById("eventSubmitBtn");
  submitBtn.disabled = true;

  const payload = {
    event_name: document.getElementById("eventName").value.trim(),
    event_date: document.getElementById("eventDate").value,
    expected_attendees: parseInt(document.getElementById("eventAttendees").value, 10),
    committee_id: parseInt(document.getElementById("eventCommitteeId").value, 10)
  };

  try {
    if (id) {
      await apiRequest(`/events/${id}`, { method: "PUT", body: payload });
      showToast("Updated", "Event updated successfully", "success");
    } else {
      await apiRequest("/events", { method: "POST", body: payload });
      showToast("Created", "New event registered successfully", "success");
    }
    closeModal("eventModal");
    await loadAllData();
  } catch (err) {
    showToast("Error", err.message, "error");
  } finally {
    submitBtn.disabled = false;
  }
}

/* ---------- Booking Modals ---------- */
function openNewBookingModal() {
  openBookingModal();
}

function openBookingModal(id = null, preselectedEventId = null) {
  const form = document.getElementById("bookingForm");
  const title = document.getElementById("bookingModalTitle");
  const statusGroup = document.getElementById("bookingStatusGroup");
  form.reset();
  document.getElementById("bookingFormId").value = "";

  populateSelectDropdowns();

  if (id) {
    const booking = state.bookings.find(b => b.request_id === id);
    if (!booking) return;
    title.textContent = `Edit Booking Request #${booking.request_id}`;
    document.getElementById("bookingFormId").value = booking.request_id;
    document.getElementById("bookingEventId").value = booking.event_id;
    document.getElementById("bookingVenueId").value = booking.venue_id;
    document.getElementById("bookingStartTime").value = toDateTimeLocalInput(booking.start_time);
    document.getElementById("bookingEndTime").value = toDateTimeLocalInput(booking.end_time);

    if (statusGroup) statusGroup.style.display = "none";
  } else {
    title.textContent = "Create Booking Request";
    if (statusGroup) statusGroup.style.display = "none";

    if (preselectedEventId) {
      document.getElementById("bookingEventId").value = preselectedEventId;
    }

    const now = new Date();
    now.setDate(now.getDate() + 1);
    now.setHours(10, 0, 0, 0);
    const startStr = now.toISOString().slice(0, 16);
    now.setHours(13, 0, 0, 0);
    const endStr = now.toISOString().slice(0, 16);
    document.getElementById("bookingStartTime").value = startStr;
    document.getElementById("bookingEndTime").value = endStr;
  }

  openModal("bookingModal");
}

async function handleBookingSubmit(e) {
  e.preventDefault();
  const id = document.getElementById("bookingFormId").value;
  const submitBtn = document.getElementById("bookingSubmitBtn");

  const startVal = document.getElementById("bookingStartTime").value;
  const endVal = document.getElementById("bookingEndTime").value;

  if (new Date(endVal) <= new Date(startVal)) {
    showToast("Invalid Timing", "End time must be strictly after start time", "warning");
    return;
  }

  submitBtn.disabled = true;

  const formatForSql = dtStr => dtStr.replace("T", " ") + (dtStr.length === 16 ? ":00" : "");

  const payload = {
    event_id: parseInt(document.getElementById("bookingEventId").value, 10),
    venue_id: parseInt(document.getElementById("bookingVenueId").value, 10),
    start_time: formatForSql(startVal),
    end_time: formatForSql(endVal)
  };

  try {
    if (id) {
      await apiRequest(`/bookings/${id}`, { method: "PUT", body: payload });
      showToast("Updated", "Booking request updated successfully", "success");
    } else {
      const res = await apiRequest("/bookings", { method: "POST", body: payload });
      showToast("Requested", `Booking request #${res.request_id} created with 4-stage workflow`, "success");
    }
    closeModal("bookingModal");
    await loadAllData();
  } catch (err) {
    showToast("Booking Conflict", err.message, "error");
  } finally {
    submitBtn.disabled = false;
  }
}

/* ---------- Delete Confirmation ---------- */
function confirmDelete(type, id, displayName) {
  state.deleteTarget = { type, id, displayName };
  const msg = document.getElementById("deleteModalMessage");
  msg.innerHTML = `Are you sure you want to permanently delete <strong>${escapeHtml(displayName)}</strong>?<br><span style="font-size: 0.8rem; color: #dc2626;">This action cannot be undone.</span>`;

  const confirmBtn = document.getElementById("deleteConfirmBtn");
  confirmBtn.onclick = executeDelete;

  openModal("deleteModal");
}

async function executeDelete() {
  if (!state.deleteTarget) return;
  const { type, id, displayName } = state.deleteTarget;
  const confirmBtn = document.getElementById("deleteConfirmBtn");
  confirmBtn.disabled = true;

  try {
    let endpoint = "";
    if (type === "committee") endpoint = `/committees/${id}`;
    else if (type === "venue") endpoint = `/venues/${id}`;
    else if (type === "event") endpoint = `/events/${id}`;
    else if (type === "booking") endpoint = `/bookings/${id}`;

    await apiRequest(endpoint, { method: "DELETE" });
    showToast("Deleted", `${displayName} has been removed.`, "success");
    closeModal("deleteModal");
    state.deleteTarget = null;
    await loadAllData();
  } catch (err) {
    showToast("Cannot Delete", err.message, "error");
  } finally {
    confirmBtn.disabled = false;
  }
}

// =============================================================================
// Toast Feedback System
// =============================================================================

function showToast(title, message, type = "info", duration = 3500) {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;

  const iconMap = {
    success: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>',
    error: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>',
    warning: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>',
    info: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>'
  };

  toast.innerHTML = `
    ${iconMap[type] || iconMap.info}
    <div class="toast-content">
      <div class="toast-title">${escapeHtml(title)}</div>
      <div class="toast-message">${escapeHtml(message)}</div>
    </div>
    <button class="toast-close-btn" onclick="this.parentElement.remove()" aria-label="Dismiss">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 14px; height: 14px;">
        <line x1="18" y1="6" x2="6" y2="18"></line>
        <line x1="6" y1="6" x2="18" y2="18"></line>
      </svg>
    </button>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    if (toast.parentElement) {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(-10px)";
      toast.style.transition = "all 0.25s ease";
      setTimeout(() => toast.remove(), 250);
    }
  }, duration);
}

// =============================================================================
// Formatters & Utility Helpers
// =============================================================================

function renderStatusBadge(status) {
  if (!status) status = "Pending";
  const norm = status.toLowerCase();

  if (norm === "approved") {
    return `<span class="badge badge-approved"><span class="badge-dot"></span>Approved</span>`;
  } else if (norm === "rejected") {
    return `<span class="badge badge-rejected"><span class="badge-dot"></span>Rejected</span>`;
  }
  return `<span class="badge badge-pending"><span class="badge-dot"></span>Pending</span>`;
}

function formatDate(dateStr) {
  if (!dateStr) return "N/A";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric"
  });
}

function formatDateTime(dateTimeStr) {
  if (!dateTimeStr) return "N/A";
  const d = new Date(dateTimeStr);
  if (isNaN(d.getTime())) return dateTimeStr;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true
  });
}

function toDateInput(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return "";
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function toDateTimeLocalInput(dateTimeStr) {
  if (!dateTimeStr) return "";
  const d = new Date(dateTimeStr);
  if (isNaN(d.getTime())) return "";
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const hours = String(d.getHours()).padStart(2, "0");
  const minutes = String(d.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function setText(elementId, text) {
  const el = document.getElementById(elementId);
  if (el) el.textContent = text;
}

function escapeHtml(str) {
  if (!str && str !== 0) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function escapeQuote(str) {
  if (!str && str !== 0) return "";
  return String(str).replace(/'/g, "\\'").replace(/"/g, '\\"');
}

// =============================================================================
// App Initialization
// =============================================================================

window.addEventListener("DOMContentLoaded", async () => {
  // Attach wheel-containment listeners to all modal bodies (prevents background scroll)
  attachModalWheelContainment();

  window.addEventListener("hashchange", () => {
    const hash = window.location.hash.replace("#", "");
    if (hash && viewMetadata[hash]) {
      navigateTo(hash);
    }
  });

  // 1. Initialize user from backend server session
  await initCurrentUser();

  // 2. Load dataset
  await loadAllData();

  // 3. Set starting view
  const initialHash = window.location.hash.replace("#", "");
  const defaultView = (state.currentUser && state.currentUser.user_type === "APPROVAL_USER") ? "approvals" : "bookings";
  const startView = (initialHash && viewMetadata[initialHash]) ? initialHash : defaultView;
  navigateTo(startView);
});
