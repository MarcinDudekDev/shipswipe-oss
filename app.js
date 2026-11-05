(function () {
  "use strict";

  var STORAGE_KEY = "shipswipe";

  var ROSTER = [
    {
      id: "maya",
      role: "builder",
      name: "Maya Chen",
      label: "Indie SaaS Builder",
      bio: "Solo-shipping a B2B invoicing tool; product works, zero distribution plan.",
      building: "B2B invoicing tool",
      lookingFor: "someone to own distribution",
      terms: "rev-share",
      links: ["Product Hunt", "Indie Hackers"],
      tags: ["React", "Stripe", "Bootstrapped"],
      likedYou: true,
    },
    {
      id: "jonas",
      role: "builder",
      name: "Jonas Okonkwo",
      label: "Full-Stack Founder",
      bio: "MVP for open-source API analytics; wants a GTM co-pilot.",
      building: "Open-source API analytics",
      lookingFor: "GTM co-pilot for launch",
      terms: "equity",
      links: ["GitHub", "Dev community"],
      tags: ["Node.js", "Open source", "DevTools"],
      likedYou: false,
    },
    {
      id: "priya",
      role: "builder",
      name: "Priya Desai",
      label: "No-Code → Code Builder",
      bio: "Turned a Notion-template side project into a real web app; weak on marketing.",
      building: "Notion-template web app",
      lookingFor: "content marketer for organic growth",
      terms: "flexible",
      links: ["Twitter", "Notion marketplace"],
      tags: ["Next.js", "Templates", "Solo founder"],
      likedYou: false,
    },
    {
      id: "tom",
      role: "builder",
      name: "Tom Bradley",
      label: "DevTools Founder",
      bio: "Building a CI/CD dashboard for indie teams; needs someone to run launch campaigns.",
      building: "CI/CD dashboard for indie teams",
      lookingFor: "launch campaign lead",
      terms: "equity",
      links: ["Beta list", "Dev newsletter"],
      tags: ["DevTools", "CI/CD", "B2B"],
      likedYou: false,
    },
    {
      id: "sofia",
      role: "builder",
      name: "Sofia Martinez",
      label: "AI Product Builder",
      bio: "Shipping an AI writing assistant for freelancers; strong product, no audience yet.",
      building: "AI writing assistant",
      lookingFor: "paid social and email growth",
      terms: "paid",
      links: ["Landing page", "Waitlist"],
      tags: ["AI", "SaaS", "Freelance"],
      likedYou: false,
    },
    {
      id: "elena",
      role: "marketer",
      name: "Elena Vasquez",
      label: "Growth Marketer",
      bio: "Scaled two micro-SaaS past $10k MRR via SEO content and paid social.",
      building: "Content SEO and paid social channels",
      lookingFor: "technical founder with shipped product",
      terms: "rev-share",
      links: ["Growth playbook", "Case studies"],
      tags: ["Content SEO", "Paid social", "CRO"],
      likedYou: true,
    },
    {
      id: "marcus",
      role: "marketer",
      name: "Marcus Webb",
      label: "Product Marketer",
      bio: "Ex-agency PMM hunting for a technical partner to launch on rev-share.",
      building: "Positioning and launch campaigns",
      lookingFor: "builder with MVP ready to ship",
      terms: "equity",
      links: ["Portfolio", "Launch templates"],
      tags: ["Positioning", "Launch campaigns", "Email"],
      likedYou: false,
    },
    {
      id: "aisha",
      role: "marketer",
      name: "Aisha Rahman",
      label: "Community Growth",
      bio: "Grows micro-SaaS via newsletters and creator partnerships — needs a product to push.",
      building: "Newsletters and creator partnerships",
      lookingFor: "SaaS product with clear value prop",
      terms: "paid",
      links: ["Newsletter", "Creator network"],
      tags: ["Community", "Newsletter", "Partnerships"],
      likedYou: false,
    },
    {
      id: "jake",
      role: "marketer",
      name: "Jake Morrison",
      label: "SEO Specialist",
      bio: "Organic growth expert who ranks niche SaaS on Google; looking for a builder partner.",
      building: "Technical SEO and content systems",
      lookingFor: "B2B SaaS with strong product-market fit",
      terms: "rev-share",
      links: ["SEO audits", "Content calendar"],
      tags: ["SEO", "Content", "B2B"],
      likedYou: false,
    },
    {
      id: "nina",
      role: "marketer",
      name: "Nina Kowalski",
      label: "Paid Acquisition",
      bio: "Runs profitable Meta and Google ads for micro-SaaS; wants a product to scale.",
      building: "Paid social and search campaigns",
      lookingFor: "builder with conversion-ready landing page",
      terms: "flexible",
      links: ["Ad creative", "ROAS reports"],
      tags: ["Paid ads", "CRO", "Analytics"],
      likedYou: false,
    },
  ];

  var DEMO_USER = {
    id: "demo-builder",
    role: "builder",
    name: "Demo Builder",
    label: "Indie Builder",
    bio: "Shipping a side project and looking for a growth partner.",
    building: "Side-project SaaS",
    lookingFor: "marketer to own distribution",
    terms: "rev-share",
    links: ["Personal site"],
    tags: ["SaaS", "Indie", "Bootstrapped"],
  };

  var AVATAR_HUES = [210, 160, 280, 30, 340, 120, 45, 190, 300, 75];

  var state = {
    currentUser: null,
    liked: [],
    passed: [],
    matches: [],
    filters: {},
    history: [],
    guestView: "marketer",
  };

  var deck = [];
  var activeMatchId = null;
  var modalTriggerElement = null;
  var detailTriggerElement = null;

  function findProfile(id) {
    return ROSTER.find(function (profile) {
      return profile.id === id;
    });
  }

  function findMatch(matchId) {
    return state.matches.find(function (match) {
      return match.id === matchId;
    });
  }

  function oppositeRole(role) {
    return role === "builder" ? "marketer" : "builder";
  }

  // The side currently being browsed. Logged-in users see the opposite of their
  // own role; guests (no profile yet) browse the side they pick in the guest bar.
  function activeTargetRole() {
    if (state.currentUser) {
      return oppositeRole(state.currentUser.role);
    }
    return state.guestView === "builder" ? "builder" : "marketer";
  }

  function buildingFieldLabel(profile) {
    return profile.role === "marketer" ? "Channels" : "Building";
  }

  var ROLE_FORM_COPY = {
    builder: {
      subhead: "Builders: find a growth partner who owns distribution and launch channels.",
      buildingLabel: "What are you building?",
      buildingPlaceholder: "e.g. B2B invoicing tool",
      lookingLabel: "Looking for",
      lookingPlaceholder: "Someone to own distribution",
    },
    marketer: {
      subhead: "Marketers: find a vetted product worth promoting on your terms.",
      buildingLabel: "What channels do you run?",
      buildingPlaceholder: "e.g. Content SEO, paid social",
      lookingLabel: "Looking for",
      lookingPlaceholder: "A technical founder with shipped product",
    },
  };

  function applyRoleFormCopy(role, options) {
    options = options || {};
    var copy = ROLE_FORM_COPY[role] || ROLE_FORM_COPY.builder;

    if (options.subhead) {
      var subhead = document.querySelector("[data-role-sub]");
      if (subhead) {
        subhead.textContent = copy.subhead;
      }
    }

    var buildingId = options.buildingId || "profile-building";
    var lookingId = options.lookingId || "profile-looking";
    var buildingInput = document.getElementById(buildingId);
    var lookingInput = document.getElementById(lookingId);
    var buildingLabel = document.querySelector('label[for="' + buildingId + '"]');
    var lookingLabel = document.querySelector('label[for="' + lookingId + '"]');

    if (buildingLabel) {
      buildingLabel.textContent = copy.buildingLabel;
    }
    if (buildingInput) {
      buildingInput.setAttribute("placeholder", copy.buildingPlaceholder);
    }
    if (lookingLabel) {
      lookingLabel.textContent = copy.lookingLabel;
    }
    if (lookingInput) {
      lookingInput.setAttribute("placeholder", copy.lookingPlaceholder);
    }
  }

  function updateDeckContextCue() {
    var cue = document.querySelector("[data-deck-cue]");
    if (!cue) {
      return;
    }

    var targetRole = activeTargetRole();
    cue.textContent =
      "Showing " + (targetRole === "marketer" ? "marketers" : "builders");
    showElement(cue);
  }

  function profilePassesFilters(profile) {
    var filters = state.filters;

    if (filters.tag) {
      var hasTag = profile.tags.some(function (tag) {
        return tag.toLowerCase() === String(filters.tag).toLowerCase();
      });
      if (!hasTag) {
        return false;
      }
    }

    if (filters.terms && profile.terms !== filters.terms) {
      return false;
    }

    return true;
  }

  function rebuildDeck() {
    var targetRole = activeTargetRole();
    deck = ROSTER.filter(function (profile) {
      if (profile.role !== targetRole) {
        return false;
      }
      if (state.liked.indexOf(profile.id) !== -1) {
        return false;
      }
      if (state.passed.indexOf(profile.id) !== -1) {
        return false;
      }
      if (!profilePassesFilters(profile)) {
        return false;
      }
      return true;
    });
  }

  function persist() {
    var payload = {
      user: state.currentUser,
      liked: state.liked,
      passed: state.passed,
      matches: state.matches,
      filters: state.filters,
      history: state.history,
      guestView: state.guestView,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  }

  function loadState() {
    var raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      rebuildDeck();
      return;
    }

    try {
      var data = JSON.parse(raw);
      state.currentUser = data.user || null;
      state.liked = data.liked || [];
      state.passed = data.passed || [];
      state.matches = data.matches || [];
      state.filters = data.filters || {};
      state.history = data.history || [];
      state.guestView = data.guestView === "builder" ? "builder" : "marketer";
    } catch (error) {
      state.currentUser = null;
      state.liked = [];
      state.passed = [];
      state.matches = [];
      state.filters = {};
      state.history = [];
    }

    rebuildDeck();
  }

  function clearState() {
    state.currentUser = null;
    state.liked = [];
    state.passed = [];
    state.matches = [];
    state.filters = {};
    state.history = [];
    deck = [];
    activeMatchId = null;
  }

  function showElement(element) {
    if (!element) {
      return;
    }
    element.hidden = false;
    element.style.display = "";
  }

  function hideElement(element) {
    if (!element) {
      return;
    }
    element.hidden = true;
    element.style.display = "none";
  }

  function getInitials(name) {
    return name
      .split(" ")
      .map(function (part) {
        return part.charAt(0);
      })
      .join("")
      .slice(0, 2)
      .toUpperCase();
  }

  function avatarHue(profileId) {
    var index = ROSTER.findIndex(function (profile) {
      return profile.id === profileId;
    });
    return AVATAR_HUES[index >= 0 ? index : 0];
  }

  function createAvatar(profile) {
    var avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.style.setProperty("--avatar-hue", String(avatarHue(profile.id)));
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = getInitials(profile.name);
    return avatar;
  }

  function createTagList(tags) {
    var list = document.createElement("ul");
    list.className = "tag-list";

    tags.forEach(function (tag) {
      var item = document.createElement("li");
      item.className = "tag";
      item.textContent = tag;
      list.appendChild(item);
    });

    return list;
  }

  function populateDetailPanel(profile) {
    var panel = document.getElementById("detail-panel");
    if (!panel) {
      return;
    }

    var nameEl = panel.querySelector("[data-field='name']");
    var labelEl = panel.querySelector("[data-field='label']");
    var bioEl = panel.querySelector("[data-field='bio']");
    var buildingEl = panel.querySelector("[data-field='building']");
    var lookingEl = panel.querySelector("[data-field='lookingFor']");
    var termsEl = panel.querySelector("[data-field='terms']");
    var tagsEl = panel.querySelector("[data-field='tags']");

    if (nameEl) {
      nameEl.textContent = profile.name;
    }
    if (labelEl) {
      labelEl.textContent = profile.label;
    }
    if (bioEl) {
      bioEl.textContent = profile.bio;
    }
    var buildingDt = panel.querySelector(".detail-fields dt:first-child");
    if (buildingDt) {
      buildingDt.textContent = buildingFieldLabel(profile);
    }
    if (buildingEl) {
      buildingEl.textContent = profile.building;
    }
    if (lookingEl) {
      lookingEl.textContent = profile.lookingFor;
    }
    if (termsEl) {
      termsEl.textContent = profile.terms;
    }
    if (tagsEl) {
      tagsEl.innerHTML = "";
      tagsEl.appendChild(createTagList(profile.tags));
    }
  }

  function focusDetailPanel(panel) {
    if (!panel) {
      return;
    }

    var closeButton = panel.querySelector('[data-action="close-detail"]');
    if (closeButton) {
      closeButton.focus();
      return;
    }

    var heading = panel.querySelector("#detail-heading");
    if (heading) {
      heading.setAttribute("tabindex", "-1");
      heading.focus();
      return;
    }

    panel.setAttribute("tabindex", "-1");
    panel.focus();
  }

  function showDetailPanel(profile) {
    detailTriggerElement = document.activeElement;
    populateDetailPanel(profile);
    var panel = document.getElementById("detail-panel");
    showElement(panel);
    showElement(document.getElementById("detail-backdrop"));
    document.body.classList.add("drawer-open");
    focusDetailPanel(panel);
  }

  function hideDetailPanel() {
    hideElement(document.getElementById("detail-panel"));
    hideElement(document.getElementById("detail-backdrop"));
    document.body.classList.remove("drawer-open");

    if (detailTriggerElement && typeof detailTriggerElement.focus === "function") {
      detailTriggerElement.focus();
    }
    detailTriggerElement = null;
  }

  function createProfileCard(profile) {
    var card = document.createElement("article");
    card.className = "card";
    card.setAttribute("aria-label", profile.name);

    // Drag-direction stamps (LIKE / NOPE) revealed while swiping.
    var likeStamp = document.createElement("span");
    likeStamp.className = "card-stamp card-stamp-like";
    likeStamp.setAttribute("aria-hidden", "true");
    likeStamp.textContent = "LIKE";
    var nopeStamp = document.createElement("span");
    nopeStamp.className = "card-stamp card-stamp-nope";
    nopeStamp.setAttribute("aria-hidden", "true");
    nopeStamp.textContent = "NOPE";
    card.appendChild(likeStamp);
    card.appendChild(nopeStamp);

    // Single top-corner button that opens the drawer with the secondary details.
    var drawerButton = document.createElement("button");
    drawerButton.type = "button";
    drawerButton.className = "card-drawer-toggle";
    drawerButton.setAttribute("data-action", "details");
    drawerButton.setAttribute("aria-label", "View full details for " + profile.name);
    drawerButton.innerHTML = '<span aria-hidden="true">⋯</span> Details';
    card.appendChild(drawerButton);

    var header = document.createElement("header");
    header.className = "card-header";
    header.appendChild(createAvatar(profile));

    var identity = document.createElement("div");
    identity.className = "card-identity";

    var name = document.createElement("h2");
    name.className = "card-name";
    name.textContent = profile.name;

    var label = document.createElement("p");
    label.className = "card-label";
    label.textContent = profile.label;

    identity.appendChild(name);
    identity.appendChild(label);

    if (profile.likedYou) {
      var badge = document.createElement("p");
      badge.className = "card-badge-inline";
      badge.textContent = "Already liked you";
      identity.appendChild(badge);
    }

    header.appendChild(identity);
    card.appendChild(header);

    var bio = document.createElement("p");
    bio.className = "card-bio";
    bio.textContent = profile.bio;
    card.appendChild(bio);

    // The one piece of matching info that stays on the front of the card.
    var looking = document.createElement("p");
    looking.className = "card-looking";
    var lookingLabel = document.createElement("span");
    lookingLabel.className = "card-looking-label";
    lookingLabel.textContent = "Looking for";
    looking.appendChild(lookingLabel);
    looking.appendChild(document.createTextNode(profile.lookingFor));
    card.appendChild(looking);

    return card;
  }

  function hasActiveFilter() {
    return !!(state.filters.tag || state.filters.terms);
  }

  function updateSwipeButtons() {
    var passButton = document.getElementById("btn-pass");
    var likeButton = document.getElementById("btn-like");
    var undoButton = document.getElementById("btn-undo");
    var disabled = deck.length === 0;

    if (passButton) {
      passButton.disabled = disabled;
    }
    if (likeButton) {
      likeButton.disabled = disabled;
    }
    if (undoButton) {
      undoButton.disabled = state.history.length === 0;
    }
  }

  function updateEmptyStateCopy() {
    var emptyState = document.getElementById("empty-state");
    if (!emptyState) {
      return;
    }

    var message = emptyState.querySelector(".empty-state-message");
    var clearButton = emptyState.querySelector('[data-action="clear-filter"]');

    if (hasActiveFilter()) {
      if (message) {
        message.textContent =
          "No profiles match your current filter. Try a different tag or terms, or clear the filter to see everyone.";
      }
      if (clearButton) {
        showElement(clearButton);
      }
      return;
    }

    if (message) {
      message.textContent =
        "You have seen everyone for now. Check back later or update your profile.";
    }
    if (clearButton) {
      hideElement(clearButton);
    }
  }

  function setDiscoverUiVisible(visible) {
    document.querySelectorAll("[data-discover-ui]").forEach(function (element) {
      if (visible) {
        showElement(element);
      } else {
        hideElement(element);
      }
    });
  }

  function updateGuestBar() {
    var bar = document.getElementById("guest-bar");
    if (!bar) {
      return;
    }

    // The guest bar only appears for visitors without a profile. Once they
    // create one, the deck follows their own role and the bar disappears.
    if (state.currentUser) {
      hideElement(bar);
      return;
    }

    showElement(bar);
    bar.querySelectorAll("[data-guest-view]").forEach(function (button) {
      var pressed = button.getAttribute("data-guest-view") === state.guestView;
      button.setAttribute("aria-pressed", String(pressed));
    });
  }

  function renderDiscoverView() {
    var deckElement = document.getElementById("deck");
    var gate = document.getElementById("need-profile");

    if (!deckElement) {
      return;
    }

    // No profile required to browse — guests can swipe straight away.
    if (gate) {
      hideElement(gate);
    }
    setDiscoverUiVisible(true);
    updateGuestBar();
    updateDeckContextCue();
    renderDeck();
  }

  function renderDeck() {
    var deckElement = document.getElementById("deck");
    if (!deckElement) {
      return;
    }

    deckElement.innerHTML = "";
    hideDetailPanel();

    var emptyState = document.getElementById("empty-state");
    if (deck.length === 0) {
      var activeEl = document.activeElement;
      var focusWasOnSwipeButton =
        activeEl &&
        (activeEl.id === "btn-like" || activeEl.id === "btn-pass");

      updateEmptyStateCopy();
      showElement(emptyState);
      updateSwipeButtons();

      if (focusWasOnSwipeButton && emptyState) {
        var message = emptyState.querySelector(".empty-state-message");
        if (message) {
          message.setAttribute("tabindex", "-1");
          message.focus();
        }
      }
      return;
    }

    hideElement(emptyState);
    var card = createProfileCard(deck[0]);
    deckElement.appendChild(card);
    attachSwipeGestures(card);
    updateSwipeButtons();
  }

  // Pointer-based drag-to-swipe so the deck genuinely works by swiping on a
  // phone (not just the Pass/Like buttons). Pointer events cover touch + mouse.
  function attachSwipeGestures(card) {
    var startX = 0;
    var startY = 0;
    var dx = 0;
    var dy = 0;
    var dragging = false;
    var SWIPE_THRESHOLD = 88;

    function setProgress() {
      card.style.transform =
        "translate(" + dx + "px, " + dy * 0.35 + "px) rotate(" + dx / 18 + "deg)";
      var ratio = Math.min(Math.abs(dx) / 120, 1);
      card.style.setProperty("--like-progress", dx > 0 ? ratio : 0);
      card.style.setProperty("--nope-progress", dx < 0 ? ratio : 0);
    }

    function reset() {
      card.style.transform = "";
      card.style.setProperty("--like-progress", 0);
      card.style.setProperty("--nope-progress", 0);
    }

    function onPointerDown(event) {
      // Let the drawer button / links behave normally.
      if (event.target.closest("button, a")) {
        return;
      }
      if (typeof event.button === "number" && event.button !== 0) {
        return;
      }
      dragging = true;
      startX = event.clientX;
      startY = event.clientY;
      dx = 0;
      dy = 0;
      card.classList.add("is-dragging");
      if (card.setPointerCapture) {
        card.setPointerCapture(event.pointerId);
      }
    }

    function onPointerMove(event) {
      if (!dragging) {
        return;
      }
      dx = event.clientX - startX;
      dy = event.clientY - startY;
      setProgress();
    }

    function onPointerUp() {
      if (!dragging) {
        return;
      }
      dragging = false;
      card.classList.remove("is-dragging");

      if (dx > SWIPE_THRESHOLD) {
        reset();
        App.swipe("like", { animate: true });
      } else if (dx < -SWIPE_THRESHOLD) {
        reset();
        App.swipe("pass", { animate: true });
      } else {
        reset();
      }
    }

    card.addEventListener("pointerdown", onPointerDown);
    card.addEventListener("pointermove", onPointerMove);
    card.addEventListener("pointerup", onPointerUp);
    card.addEventListener("pointercancel", onPointerUp);
  }

  function populateMatchModal(profile) {
    var modal = document.getElementById("match-modal");
    if (!modal) {
      return;
    }

    var title = modal.querySelector(".match-modal-title");
    if (title) {
      title.textContent = "It's a match with " + profile.name + "!";
    }

    var body = modal.querySelector(".match-modal-body");
    if (body) {
      body.textContent =
        "You both swiped right. Connect and start planning your launch together.";
    }
  }

  function getFocusableElements(container) {
    return Array.prototype.slice
      .call(
        container.querySelectorAll(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        )
      )
      .filter(function (element) {
        return !element.disabled && element.offsetParent !== null;
      });
  }

  function focusModal(modal) {
    var focusable = getFocusableElements(modal);
    if (focusable.length > 0) {
      focusable[0].focus();
      return;
    }
    modal.setAttribute("tabindex", "-1");
    modal.focus();
  }

  function showMatchModal(profile) {
    var modal = document.getElementById("match-modal");
    if (!modal) {
      return;
    }

    modalTriggerElement = document.activeElement;
    populateMatchModal(profile);
    showElement(modal);
    focusModal(modal);
  }

  function hideMatchModal() {
    var modal = document.getElementById("match-modal");
    if (!modal) {
      return;
    }

    hideElement(modal);

    if (modalTriggerElement && typeof modalTriggerElement.focus === "function") {
      modalTriggerElement.focus();
    }
    modalTriggerElement = null;
  }

  function handleDialogKeydown(event, panel, hidePanel) {
    if (!panel || panel.hidden) {
      return false;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      hidePanel();
      return true;
    }

    if (event.key !== "Tab") {
      return true;
    }

    var focusable = getFocusableElements(panel);
    if (focusable.length === 0) {
      return true;
    }

    var first = focusable[0];
    var last = focusable[focusable.length - 1];

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
      return true;
    }

    if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }

    return true;
  }

  function handleModalKeydown(event) {
    var detailPanel = document.getElementById("detail-panel");
    if (detailPanel && !detailPanel.hidden) {
      handleDialogKeydown(event, detailPanel, hideDetailPanel);
      return;
    }

    var modal = document.getElementById("match-modal");
    if (modal && !modal.hidden) {
      handleDialogKeydown(event, modal, hideMatchModal);
    }
  }

  function prefersReducedMotion() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function handleDiscoverKeydown(event) {
    var matchModal = document.getElementById("match-modal");
    if (matchModal && !matchModal.hidden) {
      return;
    }

    var detailPanel = document.getElementById("detail-panel");
    if (detailPanel && !detailPanel.hidden) {
      return;
    }

    var ae = document.activeElement;
    if (ae && /^(INPUT|SELECT|TEXTAREA)$/.test(ae.tagName)) {
      return;
    }

    if (deck.length === 0) {
      return;
    }

    if (event.key === "ArrowLeft") {
      event.preventDefault();
      App.swipe("pass", { animate: true });
      return;
    }

    if (event.key === "ArrowRight") {
      event.preventDefault();
      App.swipe("like", { animate: true });
    }
  }

  function populateConnectPanel(profile, match) {
    var panel = document.getElementById("connect-panel");
    if (!panel || !profile) {
      return;
    }

    var heading = panel.querySelector("#connect-heading");
    if (heading) {
      heading.textContent = "Connect with " + profile.name;
    }

    var contact = panel.querySelector("#connect-contact");
    if (contact) {
      var contactText =
        "Contact: " + profile.name + " · " + profile.label + " · Terms: " + profile.terms;
      if (profile.links && profile.links.length) {
        contactText +=
          " Find " + profile.name + " on: " + profile.links.join(" · ");
      }
      contact.textContent = contactText;
    }

    var context = panel.querySelector(".connect-context");
    if (!context) {
      context = document.createElement("p");
      context.className = "connect-context";
      if (contact) {
        contact.insertAdjacentElement("afterend", context);
      } else {
        panel.appendChild(context);
      }
    }
    context.textContent =
      profile.name + " is looking for: " + (profile.lookingFor || "a launch partner");
    if (profile.building) {
      context.textContent += ". " + profile.building + ".";
    }

    var introField = panel.querySelector("#intro-message");
    if (introField && match && match.intro) {
      introField.value = match.intro;
    } else if (introField) {
      introField.value = "";
    }

    var introSent = panel.querySelector("#intro-sent");
    if (introSent) {
      introSent.hidden = true;
      introSent.textContent = "";
    }
  }

  function showConnectPanel(matchId) {
    var profile = findProfile(matchId);
    var match = findMatch(matchId);
    if (!profile || !match) {
      return;
    }

    activeMatchId = matchId;
    populateConnectPanel(profile, match);
    showElement(document.getElementById("connect-panel"));
  }

  function hideConnectPanel() {
    hideElement(document.getElementById("connect-panel"));
    activeMatchId = null;
  }

  function createMatchRow(match) {
    var profile = findProfile(match.id);
    if (!profile) {
      return document.createDocumentFragment();
    }

    var row = document.createElement("article");
    row.className = "match-row";
    row.dataset.matchId = match.id;

    row.appendChild(createAvatar(profile));

    var details = document.createElement("div");
    details.className = "match-details";

    var name = document.createElement("h2");
    name.className = "match-name";
    name.textContent = profile.name;

    var partnership = document.createElement("p");
    partnership.className = "match-label";
    partnership.textContent = profile.label + " · " + profile.terms;

    var building = document.createElement("p");
    building.className = "match-building";
    building.textContent = profile.building;

    details.appendChild(name);
    details.appendChild(partnership);
    details.appendChild(building);
    row.appendChild(details);

    var connectButton = document.createElement("button");
    connectButton.type = "button";
    connectButton.className = "btn-connect";
    connectButton.setAttribute("data-action", "connect");
    connectButton.setAttribute("data-match-id", match.id);
    connectButton.setAttribute("aria-label", "Connect with " + profile.name);
    connectButton.textContent = match.connected ? "Connected" : "Connect";
    row.appendChild(connectButton);

    return row;
  }

  function setMatchesUiVisible(visible) {
    document.querySelectorAll("[data-matches-ui]").forEach(function (element) {
      if (visible) {
        showElement(element);
      } else {
        hideElement(element);
      }
    });
  }

  function renderMatchesGate() {
    var list = document.getElementById("matches-list");

    // Page-scoped: only run on the Matches page, never on Discover (which shares
    // the #need-profile element but must stay open to guests).
    if (!list) {
      return;
    }

    var gate = document.getElementById("need-profile");

    if (!state.currentUser) {
      if (gate) {
        showElement(gate);
      }
      setMatchesUiVisible(false);
      hideConnectPanel();
      if (list) {
        list.innerHTML = "";
      }
      return;
    }

    if (gate) {
      hideElement(gate);
    }
    setMatchesUiVisible(true);
    renderMatches();
  }

  function renderMatches() {
    var list = document.getElementById("matches-list");
    if (!list) {
      return;
    }

    list.innerHTML = "";

    if (state.matches.length === 0) {
      var empty = document.createElement("p");
      empty.className = "matches-empty";
      empty.innerHTML =
        'No matches yet. <a href="discover.html">Head to Discover</a> and start swiping.';
      list.appendChild(empty);
      return;
    }

    state.matches.forEach(function (match) {
      list.appendChild(createMatchRow(match));
    });
  }

  function renderProfileGate() {
    // Page-scoped: only run on the Profile page. The shared #need-profile element
    // also lives on Discover, which must stay open to guests.
    if (!document.getElementById("profile-view") && !document.getElementById("profile-edit-form")) {
      return;
    }

    var gate = document.getElementById("need-profile");
    var profileUi = document.querySelectorAll("[data-profile-ui]");

    if (!gate) {
      renderProfileView();
      fillProfileForm();
      return;
    }

    if (!state.currentUser) {
      showElement(gate);
      profileUi.forEach(function (element) {
        hideElement(element);
      });
      return;
    }

    hideElement(gate);
    profileUi.forEach(function (element) {
      showElement(element);
    });
    renderProfileView();
    fillProfileForm();
  }

  function renderProfileView() {
    var view = document.getElementById("profile-view");
    if (!view) {
      return;
    }

    if (!state.currentUser) {
      view.innerHTML =
        '<p class="profile-empty">No profile yet. <a href="index.html">Create one on the home page</a>.</p>';
      return;
    }

    var user = state.currentUser;
    view.innerHTML = "";

    var header = document.createElement("header");
    header.className = "profile-header";
    header.appendChild(createAvatar({ id: user.id || "user", name: user.name }));

    var identity = document.createElement("div");
    var name = document.createElement("h2");
    name.textContent = user.name;
    var label = document.createElement("p");
    label.className = "profile-label";
    label.textContent = user.label || user.role;
    identity.appendChild(name);
    identity.appendChild(label);
    header.appendChild(identity);
    view.appendChild(header);

    var dl = document.createElement("dl");
    dl.className = "profile-fields";

    function addField(term, value) {
      if (!value) {
        return;
      }
      var dt = document.createElement("dt");
      dt.textContent = term;
      var dd = document.createElement("dd");
      dd.textContent = value;
      dl.appendChild(dt);
      dl.appendChild(dd);
    }

    addField("Role", user.role);
    addField("Bio", user.bio);
    addField("Building", user.building);
    addField("Looking for", user.lookingFor);
    addField("Terms", user.terms);
    if (user.tags && user.tags.length) {
      addField("Tags", user.tags.join(", "));
    }
    if (user.links && user.links.length) {
      addField("Links", user.links.join(", "));
    }

    view.appendChild(dl);
  }

  function fillProfileForm() {
    var form = document.getElementById("profile-edit-form");
    if (!form || !state.currentUser) {
      return;
    }

    var user = state.currentUser;
    var setValue = function (id, value) {
      var field = document.getElementById(id);
      if (field) {
        field.value = value || "";
      }
    };

    setValue("edit-name", user.name);
    setValue("edit-label", user.label);
    setValue("edit-bio", user.bio);
    setValue("edit-building", user.building);
    setValue("edit-looking", user.lookingFor);
    setValue("edit-terms", user.terms);
    setValue("edit-tags", user.tags ? user.tags.join(", ") : "");
    setValue("edit-links", user.links ? user.links.join(", ") : "");

    var roleField = form.querySelector('input[name="edit-role"][value="' + user.role + '"]');
    if (roleField) {
      roleField.checked = true;
    }
  }

  function resetSwipeState() {
    state.liked = [];
    state.passed = [];
    state.matches = [];
    state.history = [];
    rebuildDeck();
    hideMatchModal();
    hideDetailPanel();
    hideConnectPanel();
  }

  function normalizeUser(profile) {
    return {
      id: profile.id || "user-" + Date.now(),
      role: profile.role,
      name: profile.name,
      label: profile.label || "",
      bio: profile.bio || "",
      building: profile.building || "",
      lookingFor: profile.lookingFor || "",
      terms: profile.terms || "flexible",
      links: profile.links || [],
      tags: profile.tags || [],
    };
  }

  function getOppositeRoleTags() {
    if (!state.currentUser) {
      return [];
    }

    var targetRole = oppositeRole(state.currentUser.role);
    var seen = {};
    var tags = [];

    ROSTER.forEach(function (profile) {
      if (profile.role !== targetRole) {
        return;
      }

      profile.tags.forEach(function (tag) {
        var key = tag.toLowerCase();
        if (!seen[key]) {
          seen[key] = true;
          tags.push(tag);
        }
      });
    });

    tags.sort(function (a, b) {
      return a.localeCompare(b);
    });

    return tags;
  }

  function populateFilterOptions() {
    var filter = document.getElementById("filter");
    if (!filter) {
      return;
    }

    var staticOptions = Array.prototype.slice.call(filter.querySelectorAll("option")).filter(function (option) {
      return option.value === "all" || option.value.indexOf("terms:") === 0;
    });

    filter.innerHTML = "";

    staticOptions.forEach(function (option) {
      filter.appendChild(option);
    });

    getOppositeRoleTags().forEach(function (tag) {
      var option = document.createElement("option");
      option.value = "tag:" + tag;
      option.textContent = "Tag: " + tag;
      filter.appendChild(option);
    });
  }

  function syncFilterControl() {
    var filter = document.getElementById("filter");
    if (!filter) {
      return;
    }

    populateFilterOptions();

    if (state.filters.terms) {
      filter.value = "terms:" + state.filters.terms;
      return;
    }

    if (state.filters.tag) {
      filter.value = "tag:" + state.filters.tag;
      return;
    }

    filter.value = "all";
  }

  var App = {
    STORAGE_KEY: STORAGE_KEY,
    roster: ROSTER,

    get currentUser() {
      return state.currentUser;
    },

    get deck() {
      return deck;
    },

    get matches() {
      return state.matches.slice();
    },

    get filters() {
      return Object.assign({}, state.filters);
    },

    reset: function () {
      localStorage.removeItem(STORAGE_KEY);
      clearState();
      hideMatchModal();
      hideDetailPanel();
      hideConnectPanel();
      renderDiscoverView();
      renderMatchesGate();
      renderProfileGate();
      syncFilterControl();
    },

    seedDemo: function () {
      state.currentUser = normalizeUser(DEMO_USER);
      state.filters = {};
      resetSwipeState();
      persist();
      renderDiscoverView();
      syncFilterControl();
      return state.currentUser;
    },

    createProfile: function (profile) {
      if (!profile || !profile.role || !profile.name) {
        return null;
      }

      state.currentUser = normalizeUser(profile);
      state.filters = {};
      resetSwipeState();
      persist();
      renderDiscoverView();
      renderMatchesGate();
      renderProfileGate();
      syncFilterControl();
      return state.currentUser;
    },

    updateProfile: function (patch) {
      if (!state.currentUser) {
        return null;
      }

      if (patch.tags && typeof patch.tags === "string") {
        patch.tags = parseTagsInput(patch.tags);
      }
      if (patch.links && typeof patch.links === "string") {
        patch.links = parseTagsInput(patch.links);
      }

      var roleChanged = patch.role && patch.role !== state.currentUser.role;
      state.currentUser = Object.assign({}, state.currentUser, patch);

      if (roleChanged) {
        state.filters = {};
        resetSwipeState();
        persist();
        renderDiscoverView();
        renderMatchesGate();
        syncFilterControl();
      } else {
        persist();
      }

      renderProfileView();
      fillProfileForm();
      return state.currentUser;
    },

    setFilters: function (filters) {
      state.filters = filters ? Object.assign({}, filters) : {};
      rebuildDeck();
      persist();
      renderDeck();
      syncFilterControl();
      return state.filters;
    },

    setGuestView: function (view) {
      if (state.currentUser) {
        return state.guestView;
      }
      state.guestView = view === "builder" ? "builder" : "marketer";
      rebuildDeck();
      persist();
      updateGuestBar();
      updateDeckContextCue();
      renderDeck();
      syncFilterControl();
      return state.guestView;
    },

    swipe: function (direction, options) {
      if (deck.length === 0) {
        return { matched: false, profile: null };
      }

      options = options || {};
      var profile = deck[0];
      var matched = false;

      if (direction === "pass") {
        state.passed.push(profile.id);
        deck.shift();
        state.history.push({ profileId: profile.id, direction: "pass", matched: false });
      } else if (direction === "like") {
        state.liked.push(profile.id);
        deck.shift();
        if (profile.likedYou) {
          state.matches.push({ id: profile.id, connected: false, intro: null });
          matched = true;
        }
        state.history.push({ profileId: profile.id, direction: "like", matched: matched });
      } else {
        return { matched: false, profile: profile };
      }

      persist();

      var cardEl = document.querySelector("#deck .card");
      var animate =
        options.animate &&
        cardEl &&
        !prefersReducedMotion() &&
        deck.length > 0 &&
        !matched;

      function finishSwipeRender() {
        renderDeck();
        if (matched) {
          showMatchModal(profile);
        }
      }

      if (animate) {
        cardEl.classList.add(direction === "like" ? "is-swiping-like" : "is-swiping-pass");
        window.setTimeout(finishSwipeRender, 280);
      } else {
        finishSwipeRender();
      }

      return { matched: matched, profile: profile };
    },

    undo: function () {
      if (state.history.length === 0) {
        return null;
      }

      var last = state.history.pop();
      var profile = findProfile(last.profileId);
      if (!profile) {
        persist();
        return null;
      }

      state.liked = state.liked.filter(function (id) {
        return id !== last.profileId;
      });
      state.passed = state.passed.filter(function (id) {
        return id !== last.profileId;
      });

      if (last.matched) {
        state.matches = state.matches.filter(function (match) {
          return match.id !== last.profileId;
        });
        hideMatchModal();
      }

      if (!profilePassesFilters(profile)) {
        persist();
        renderDeck();
        return null;
      }

      deck.unshift(profile);
      persist();
      renderDeck();
      return profile;
    },

    connect: function (matchId) {
      var match = findMatch(matchId);
      if (!match) {
        return null;
      }

      match.connected = true;
      persist();
      renderMatches();
      showConnectPanel(matchId);
      return match;
    },

    sendIntro: function (matchId, text) {
      var match = findMatch(matchId);
      if (!match) {
        return false;
      }

      match.intro = text;
      persist();
      return true;
    },

    renderMatches: renderMatches,
  };

  function parseTagsInput(value) {
    if (!value) {
      return [];
    }

    return value
      .split(",")
      .map(function (tag) {
        return tag.trim();
      })
      .filter(function (tag) {
        return tag.length > 0;
      });
  }

  function getSelectedRole(selector) {
    var selected = document.querySelector(selector);
    return selected ? selected.value : "builder";
  }

  function bindRoleFormFields(roleSelector, options) {
    options = options || {};
    var fields = document.querySelectorAll(roleSelector);
    if (fields.length === 0) {
      return;
    }

    function syncFromSelection() {
      var selected = document.querySelector(roleSelector + ":checked");
      if (selected) {
        applyRoleFormCopy(selected.value, options);
      }
    }

    fields.forEach(function (field) {
      field.addEventListener("change", syncFromSelection);
    });

    syncFromSelection();
  }

  function bindIndexPage() {
    var form = document.getElementById("profile-form");
    if (!form) {
      return;
    }

    bindRoleFormFields('input[name="role"]', { subhead: true });

    var sampleButton = document.getElementById("btn-sample");
    if (sampleButton) {
      sampleButton.addEventListener("click", function () {
        var builderRole = document.querySelector('input[name="role"][value="builder"]');
        if (builderRole) {
          builderRole.checked = true;
        }

        document.getElementById("profile-name").value = DEMO_USER.name;
        document.getElementById("profile-bio").value = DEMO_USER.bio;
        document.getElementById("profile-building").value = DEMO_USER.building;
        document.getElementById("profile-looking").value = DEMO_USER.lookingFor;
        document.getElementById("profile-terms").value = DEMO_USER.terms;
        document.getElementById("profile-tags").value = DEMO_USER.tags.join(", ");
      });
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();

      var nameInput = document.getElementById("profile-name");
      var bioInput = document.getElementById("profile-bio");
      var buildingInput = document.getElementById("profile-building");
      var lookingInput = document.getElementById("profile-looking");
      var termsInput = document.getElementById("profile-terms");
      var tagsInput = document.getElementById("profile-tags");

      var profile = {
        role: getSelectedRole('input[name="role"]:checked'),
        name: nameInput.value.trim(),
        bio: bioInput.value.trim(),
        building: buildingInput ? buildingInput.value.trim() : "",
        lookingFor: lookingInput ? lookingInput.value.trim() : "",
        terms: termsInput ? termsInput.value : "flexible",
        tags: parseTagsInput(tagsInput.value),
      };

      App.createProfile(profile);

      var prompt = document.getElementById("profile-complete-prompt");
      if (prompt && (!profile.building || !profile.lookingFor || !profile.terms)) {
        showElement(prompt);
        return;
      }

      window.location.href = "discover.html";
    });
  }

  function bindNavToggle() {
    var toggle = document.querySelector(".nav-toggle");
    var nav = document.getElementById("site-nav");
    if (!toggle || !nav) {
      return;
    }

    toggle.addEventListener("click", function () {
      var expanded = toggle.getAttribute("aria-expanded") === "true";
      var nextExpanded = !expanded;
      toggle.setAttribute("aria-expanded", String(nextExpanded));
      nav.classList.toggle("is-open", nextExpanded);
    });
  }

  function bindGlobalKeyboard() {
    document.addEventListener("keydown", function (event) {
      handleModalKeydown(event);
      if (document.getElementById("deck")) {
        handleDiscoverKeydown(event);
      }
    });
  }

  function bindDiscoverPage() {
    var passButton = document.getElementById("btn-pass");
    var likeButton = document.getElementById("btn-like");
    var undoButton = document.getElementById("btn-undo");
    var filter = document.getElementById("filter");
    var deckElement = document.getElementById("deck");
    var detailPanel = document.getElementById("detail-panel");

    if (passButton) {
      passButton.addEventListener("click", function () {
        App.swipe("pass", { animate: true });
      });
    }

    if (likeButton) {
      likeButton.addEventListener("click", function () {
        App.swipe("like", { animate: true });
      });
    }

    if (undoButton) {
      undoButton.addEventListener("click", function () {
        App.undo();
      });
    }

    if (filter) {
      filter.addEventListener("change", function () {
        var value = filter.value;
        if (value === "all") {
          App.setFilters({});
          return;
        }

        var parts = value.split(":");
        if (parts[0] === "terms") {
          App.setFilters({ terms: parts[1] });
          return;
        }

        if (parts[0] === "tag") {
          App.setFilters({ tag: parts[1] });
        }
      });
    }

    var guestBar = document.getElementById("guest-bar");
    if (guestBar) {
      guestBar.addEventListener("click", function (event) {
        var target = event.target;
        if (!(target instanceof HTMLElement)) {
          return;
        }
        var pill = target.closest("[data-guest-view]");
        if (pill) {
          App.setGuestView(pill.getAttribute("data-guest-view"));
        }
      });
    }

    var detailBackdrop = document.getElementById("detail-backdrop");
    if (detailBackdrop) {
      detailBackdrop.addEventListener("click", function () {
        hideDetailPanel();
      });
    }

    var clearFilterButton = document.querySelector('[data-action="clear-filter"]');
    if (clearFilterButton) {
      clearFilterButton.addEventListener("click", function () {
        App.setFilters({});
      });
    }

    if (deckElement) {
      deckElement.addEventListener("click", function (event) {
        var target = event.target;
        if (!(target instanceof HTMLElement)) {
          return;
        }

        var trigger = target.closest('[data-action="details"]');
        if (trigger && deck[0]) {
          showDetailPanel(deck[0]);
        }
      });
    }

    if (detailPanel) {
      detailPanel.addEventListener("click", function (event) {
        var target = event.target;
        if (!(target instanceof HTMLElement)) {
          return;
        }

        if (target.getAttribute("data-action") === "close-detail") {
          hideDetailPanel();
        }
      });
    }

    var modal = document.getElementById("match-modal");
    if (modal) {
      modal.addEventListener("click", function (event) {
        var target = event.target;
        if (!(target instanceof HTMLElement)) {
          return;
        }

        var action = target.getAttribute("data-action");
        if (action === "connect") {
          hideMatchModal();
          window.location.href = "matches.html";
        } else if (action === "close") {
          hideMatchModal();
        }
      });
    }
  }

  function bindMatchesPage() {
    var list = document.getElementById("matches-list");
    var panel = document.getElementById("connect-panel");

    if (list) {
      list.addEventListener("click", function (event) {
        var target = event.target;
        if (!(target instanceof HTMLElement)) {
          return;
        }

        if (target.getAttribute("data-action") === "connect") {
          var matchId = target.getAttribute("data-match-id");
          if (matchId) {
            App.connect(matchId);
          }
        }
      });
    }

    if (panel) {
      panel.addEventListener("click", function (event) {
        var target = event.target;
        if (!(target instanceof HTMLElement)) {
          return;
        }

        if (target.getAttribute("data-action") === "send-intro" && activeMatchId) {
          var introField = document.getElementById("intro-message");
          var text = introField ? introField.value.trim() : "";
          var status = document.getElementById("intro-sent");
          if (!text) {
            if (status) {
              status.hidden = true;
              status.textContent = "";
            }
            return;
          }
          App.sendIntro(activeMatchId, text);
          if (status) {
            status.textContent = "Intro saved locally on your device.";
            showElement(status);
          }
        } else if (target.getAttribute("data-action") === "close-connect") {
          hideConnectPanel();
        }
      });
    }
  }

  function bindProfilePage() {
    var form = document.getElementById("profile-edit-form");
    if (!form) {
      return;
    }

    bindRoleFormFields('input[name="edit-role"]', {
      buildingId: "edit-building",
      lookingId: "edit-looking",
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();

      App.updateProfile({
        role: getSelectedRole('input[name="edit-role"]:checked'),
        name: document.getElementById("edit-name").value.trim(),
        label: document.getElementById("edit-label").value.trim(),
        bio: document.getElementById("edit-bio").value.trim(),
        building: document.getElementById("edit-building").value.trim(),
        lookingFor: document.getElementById("edit-looking").value.trim(),
        terms: document.getElementById("edit-terms").value,
        tags: parseTagsInput(document.getElementById("edit-tags").value),
        links: parseTagsInput(document.getElementById("edit-links").value),
      });
    });
  }

  function renderDemoBanner() {
    if (document.querySelector(".demo-banner")) {
      return;
    }
    var banner = document.createElement("div");
    banner.className = "demo-banner";
    banner.setAttribute("role", "note");
    banner.innerHTML =
      '<strong>Demo only.</strong> This is an interactive showcase — profiles are ' +
      "sample data, matches are simulated, and intros are saved in your browser only " +
      "(nothing is sent and no account is created). Real builder–marketer matching " +
      "is coming soon.";
    document.body.insertBefore(banner, document.body.firstChild);
  }

  function initPage() {
    loadState();
    renderDemoBanner();
    bindNavToggle();
    bindGlobalKeyboard();
    bindIndexPage();
    bindDiscoverPage();
    bindMatchesPage();
    bindProfilePage();
    renderDiscoverView();
    renderMatchesGate();
    renderProfileGate();
    syncFilterControl();
  }

  window.App = App;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPage);
  } else {
    initPage();
  }
})();