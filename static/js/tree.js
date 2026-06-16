(function () {
  'use strict';

  const TREE_DATA = window.TREE_DATA || { people: [], root_id: null };
  const people = TREE_DATA.people || [];
  const root_id = TREE_DATA.root_id || null;
  const peopleMap = new Map();
  people.forEach((p) => peopleMap.set(p.id, p));

  let expandedNodes = new Set(root_id ? [root_id] : []);
  let scale = 1;
  let panX = 0;
  let panY = 0;
  const minScale = 0.3;
  const maxScale = 2.5;

  const wrap = document.getElementById('canvas-wrap');
  const canvas = document.getElementById('canvas');
  const svg = document.getElementById('tree-svg');
  const nodesContainer = document.getElementById('nodes-container');
  const labelsContainer = document.getElementById('labels-container');
  const detailOverlay = document.getElementById('detail-overlay');
  const detailPanel = document.getElementById('detail-panel');

  // -------------------------------------------------------------------------
  // Core algorithm
  // -------------------------------------------------------------------------

  function getVisibleNodes() {
    const visible = new Set();
    if (root_id) visible.add(root_id);

    expandedNodes.forEach((id) => {
      const person = peopleMap.get(id);
      if (!person) return;
      if (person.father_id) visible.add(person.father_id);
      if (person.mother_id) visible.add(person.mother_id);
      if (person.partner_id) visible.add(person.partner_id);
      person.sibling_ids.forEach((sid) => visible.add(sid));
      person.child_ids.forEach((cid) => visible.add(cid));
    });

    // Reveal extended relatives: siblings' children, parents' siblings,
    // and aunts'/uncles' children so the tree feels fuller.
    const firstPass = Array.from(visible);
    firstPass.forEach((id) => {
      const person = peopleMap.get(id);
      if (!person) return;

      person.sibling_ids.forEach((sid) => {
        const sibling = peopleMap.get(sid);
        if (sibling) {
          sibling.child_ids.forEach((cid) => visible.add(cid));
        }
      });

      [person.father_id, person.mother_id].forEach((pid) => {
        if (!pid) return;
        const parent = peopleMap.get(pid);
        if (parent) {
          parent.sibling_ids.forEach((aid) => visible.add(aid));
        }
      });
    });

    const secondPass = Array.from(visible);
    secondPass.forEach((id) => {
      const person = peopleMap.get(id);
      if (!person) return;
      [person.father_id, person.mother_id].forEach((pid) => {
        if (!pid) return;
        const parent = peopleMap.get(pid);
        if (parent) {
          parent.sibling_ids.forEach((aid) => {
            const auntUncle = peopleMap.get(aid);
            if (auntUncle) {
              auntUncle.child_ids.forEach((cid) => visible.add(cid));
            }
          });
        }
      });
    });

    return visible;
  }

  function getHiddenCount(personId, visibleIds) {
    const person = peopleMap.get(personId);
    if (!person) return 0;
    const allRelatives = [
      person.father_id,
      person.mother_id,
      person.partner_id,
      ...person.sibling_ids,
      ...person.child_ids,
    ].filter(Boolean);
    return allRelatives.filter((rid) => !visibleIds.has(rid)).length;
  }

  const nodeSpacing = 160;
  const genSpacing = 260;
  const canvasPaddingX = 200;
  const canvasPaddingY = 140;

  function computeCanvasSize(visibleIds) {
    const genGroups = {};
    visibleIds.forEach((id) => {
      const person = peopleMap.get(id);
      if (!person) return;
      if (!genGroups[person.generation]) genGroups[person.generation] = 0;
      genGroups[person.generation]++;
    });

    const maxRowCount = Math.max(1, ...Object.values(genGroups));
    const rowCount = Object.keys(genGroups).length;

    const minWidth = window.innerWidth;
    const minHeight = window.innerHeight - 100;
    const contentWidth = maxRowCount * nodeSpacing + canvasPaddingX * 2;
    const contentHeight = rowCount * genSpacing + canvasPaddingY * 2;

    return {
      width: Math.max(minWidth, contentWidth),
      height: Math.max(minHeight, contentHeight),
      genGroups,
    };
  }

  function calculatePositions(visibleIds, canvasWidth, canvasHeight) {
    const positions = {};
    const genGroups = {};

    visibleIds.forEach((id) => {
      const person = peopleMap.get(id);
      if (!person) return;
      const gen = person.generation;
      if (!genGroups[gen]) genGroups[gen] = [];
      genGroups[gen].push(id);
    });

    const gens = Object.keys(genGroups)
      .map(Number)
      .sort((a, b) => b - a);
    const centerX = canvasWidth / 2;
    const centerY = canvasHeight / 2;

    gens.forEach((gen) => {
      const ids = genGroups[gen];
      const y = centerY - gen * genSpacing;
      const totalWidth = ids.length * nodeSpacing;
      const startX = centerX - totalWidth / 2 + nodeSpacing / 2;

      ids.forEach((id, i) => {
        positions[id] = { x: startX + i * nodeSpacing, y: y };
      });
    });

    return { positions, genGroups };
  }

  function fitTreeToScreen(canvasWidth, canvasHeight) {
    const header = document.getElementById('tree-header');
    const headerHeight = header ? header.getBoundingClientRect().height : 64;
    const availableHeight = window.innerHeight - headerHeight;
    const availableWidth = window.innerWidth;
    const fitScaleH = (availableHeight - 48) / canvasHeight;
    const fitScaleW = (availableWidth - 48) / canvasWidth;
    const fitScale = Math.min(fitScaleH, fitScaleW);
    scale = Math.max(minScale, Math.min(1, fitScale));
  }

  function setCanvasSize(width, height) {
    if (!canvas || !svg || !nodesContainer || !labelsContainer || !wrap) return;

    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    svg.setAttribute('width', width);
    svg.setAttribute('height', height);
    nodesContainer.style.width = `${width}px`;
    nodesContainer.style.height = `${height}px`;
    labelsContainer.style.width = `${width}px`;
    labelsContainer.style.height = `${height}px`;

    panX = 0;
    panY = 0;
    updateTransform();
  }

  function updateTransform() {
    if (!canvas) return;
    canvas.style.transform = `translate(-50%, -50%) translate(${panX}px, ${panY}px) scale(${scale})`;
  }

  function centerCanvas() {
    const header = document.getElementById('tree-header');
    const headerHeight = header ? header.getBoundingClientRect().height : 64;
    if (wrap) wrap.style.top = `${headerHeight}px`;
  }

  // -------------------------------------------------------------------------
  // Rendering
  // -------------------------------------------------------------------------

  function renderTree() {
    if (!wrap || !canvas || !svg || !nodesContainer || !labelsContainer) return;

    const visibleIds = getVisibleNodes();
    const { width, height } = computeCanvasSize(visibleIds);
    const { positions, genGroups } = calculatePositions(visibleIds, width, height);

    fitTreeToScreen(width, height);
    setCanvasSize(width, height);
    centerCanvas();

    nodesContainer.innerHTML = '';
    labelsContainer.innerHTML = '';
    svg.innerHTML = '';

    const drawn = new Set();
    let lineIndex = 0;

    visibleIds.forEach((id) => {
      const person = peopleMap.get(id);
      const pos = positions[id];
      if (!person || !pos) return;

      // Partner connection
      if (
        person.partner_id &&
        visibleIds.has(person.partner_id) &&
        id < person.partner_id
      ) {
        const pPos = positions[person.partner_id];
        if (pPos) {
          const key = `${pos.x},${pos.y}-${pPos.x},${pPos.y}`;
          if (!drawn.has(key)) {
            drawn.add(key);
            const path = document.createElementNS(
              'http://www.w3.org/2000/svg',
              'path'
            );
            const midY = (pos.y + pPos.y) / 2;
            path.setAttribute(
              'd',
              `M ${pos.x} ${pos.y} C ${pos.x} ${midY}, ${pPos.x} ${midY}, ${pPos.x} ${pPos.y}`
            );
            path.setAttribute('class', 'conn-line partner');
            path.style.animationDelay = `${lineIndex++ * 0.08}s`;
            svg.appendChild(path);
          }
        }
      }

      // Parent connections
      [person.father_id, person.mother_id].forEach((pid) => {
        if (pid && visibleIds.has(pid)) {
          const pPos = positions[pid];
          if (pPos) {
            const key = `${pPos.x},${pPos.y}-${pos.x},${pos.y}`;
            if (!drawn.has(key)) {
              drawn.add(key);
              const path = document.createElementNS(
                'http://www.w3.org/2000/svg',
                'path'
              );
              const midY = (pPos.y + pos.y) / 2;
              path.setAttribute(
                'd',
                `M ${pPos.x} ${pPos.y} C ${pPos.x} ${midY}, ${pos.x} ${midY}, ${pos.x} ${pos.y}`
              );
              path.setAttribute('class', 'conn-line parent');
              path.style.animationDelay = `${lineIndex++ * 0.08}s`;
              svg.appendChild(path);
            }
          }
        }
      });

      // Child connections
      person.child_ids.forEach((cid) => {
        if (cid && visibleIds.has(cid)) {
          const cPos = positions[cid];
          if (cPos) {
            const key = `${pos.x},${pos.y}-${cPos.x},${cPos.y}`;
            if (!drawn.has(key)) {
              drawn.add(key);
              const path = document.createElementNS(
                'http://www.w3.org/2000/svg',
                'path'
              );
              const midY = (pos.y + cPos.y) / 2;
              path.setAttribute(
                'd',
                `M ${pos.x} ${pos.y} C ${pos.x} ${midY}, ${cPos.x} ${midY}, ${cPos.x} ${cPos.y}`
              );
              path.setAttribute('class', 'conn-line child');
              path.style.animationDelay = `${lineIndex++ * 0.08}s`;
              svg.appendChild(path);
            }
          }
        }
      });
    });

    // Generation labels
    const genNames = {
      4: 'Great-great-grandparents',
      3: 'Great-grandparents',
      2: 'Grandparents',
      1: 'Parents',
      0: 'You',
      '-1': 'Children',
      '-2': 'Grandchildren',
      '-3': 'Great-grandchildren',
      '-4': 'Great-great-grandchildren',
    };

    Object.keys(genGroups)
      .map(Number)
      .sort((a, b) => b - a)
      .forEach((gen) => {
        const ids = genGroups[gen];
        if (!ids || ids.length === 0) return;
        const firstPos = positions[ids[0]];
        const lastPos = positions[ids[ids.length - 1]];
        if (!firstPos || !lastPos) return;
        const midX = (firstPos.x + lastPos.x) / 2;
        const y = firstPos.y - 70;

        const label = document.createElement('div');
        label.className = 'gen-label';
        label.textContent = genNames[gen] || `Generation ${gen}`;
        label.style.left = `${midX}px`;
        label.style.top = `${y}px`;
        labelsContainer.appendChild(label);
      });

    // Person nodes
    visibleIds.forEach((id) => {
      const person = peopleMap.get(id);
      const pos = positions[id];
      if (!person || !pos) return;

      const hiddenCount = getHiddenCount(id, visibleIds);
      const isExpanded = expandedNodes.has(id);
      const isRoot = id === root_id;

      const node = document.createElement('div');
      node.className = `person-node${isRoot ? ' is-root' : ''}`;
      node.style.left = `${pos.x - 34}px`;
      node.style.top = `${pos.y - 34}px`;
      node.style.animationDelay = `${Math.random() * 0.15}s`;

      const avatar = document.createElement('div');
      const genClass = isRoot
        ? 'root-avatar'
        : `gen-${String(person.generation).replace('-', 'minus')}`;
      avatar.className = `person-avatar ${genClass}`;
      if (person.avatar_url) {
        const img = document.createElement('img');
        img.src = person.avatar_url;
        img.alt = '';
        img.loading = 'lazy';
        img.onerror = function () {
          this.style.display = 'none';
        };
        avatar.appendChild(img);
      }
      const initials = document.createElement('span');
      initials.className = 'avatar-initials';
      initials.textContent = person.initials;
      avatar.appendChild(initials);
      node.appendChild(avatar);

      // Expand hint ring
      const hint = document.createElement('div');
      hint.className = 'expand-hint';
      node.appendChild(hint);

      // Badge
      if (hiddenCount > 0 || isExpanded) {
        const badge = document.createElement('div');
        badge.className = `person-badge${hiddenCount === 0 ? ' is-zero' : ''}`;
        if (hiddenCount > 0) {
          badge.textContent = hiddenCount;
        } else {
          badge.innerHTML = '<i data-lucide="check"></i>';
        }
        node.appendChild(badge);
      }

      // Name label
      const nameLabel = document.createElement('div');
      nameLabel.className = 'name-label';
      nameLabel.textContent = person.name;
      node.appendChild(nameLabel);

      // Role label
      const roleLabel = document.createElement('div');
      roleLabel.className = 'role-label';
      roleLabel.textContent = genNames[person.generation] || person.role;
      node.appendChild(roleLabel);

      node.addEventListener('click', (e) => {
        e.stopPropagation();
        if (suppressClick) return;
        if (hiddenCount > 0 && !isExpanded) {
          expandedNodes.add(id);
          renderTree();
        } else {
          openDetail(id);
        }
      });

      nodesContainer.appendChild(node);
    });

    if (typeof lucide !== 'undefined') {
      lucide.createIcons();
    }
  }

  // -------------------------------------------------------------------------
  // Pan & zoom
  // -------------------------------------------------------------------------

  let isDragging = false;
  let hasDragged = false;
  let dragStart = { x: 0, y: 0 };
  let lastPan = { x: 0, y: 0 };
  let suppressClick = false;

  let pinchStartDistance = 0;
  let pinchStartScale = 1;
  let pinchStartMid = { x: 0, y: 0 };
  let pinchStartPan = { x: 0, y: 0 };

  function clamp(val, lo, hi) {
    return Math.max(lo, Math.min(hi, val));
  }

  function getWrapCentre() {
    const rect = wrap.getBoundingClientRect();
    return { x: rect.width / 2, y: rect.height / 2, rect };
  }

  function zoomBy(factor, screenX, screenY) {
    const { x: cx, y: cy, rect } = getWrapCentre();
    const mouseOffsetX = (screenX === undefined ? cx : screenX - rect.left) - cx;
    const mouseOffsetY = (screenY === undefined ? cy : screenY - rect.top) - cy;
    const newScale = clamp(scale * factor, minScale, maxScale);
    panX += mouseOffsetX * (1 - newScale / scale);
    panY += mouseOffsetY * (1 - newScale / scale);
    scale = newScale;
    updateTransform();
  }

  function fitToScreen() {
    renderTree();
    showToast('Tree fitted to screen');
  }

  function resetView() {
    renderTree();
    showToast('View reset');
  }

  function startDrag(e) {
    if (e.button !== 0) return;
    if (!wrap) return;
    isDragging = true;
    hasDragged = false;
    dragStart.x = e.clientX;
    dragStart.y = e.clientY;
    lastPan.x = panX;
    lastPan.y = panY;
    canvas.classList.add('is-dragging');
  }

  function onDrag(e) {
    if (!isDragging) return;
    const dx = e.clientX - dragStart.x;
    const dy = e.clientY - dragStart.y;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) hasDragged = true;
    panX = lastPan.x + dx;
    panY = lastPan.y + dy;
    updateTransform();
  }

  function endDrag() {
    if (!isDragging) return;
    isDragging = false;
    canvas.classList.remove('is-dragging');
    if (hasDragged) {
      suppressClick = true;
      setTimeout(() => {
        suppressClick = false;
      }, 60);
    }
  }

  function onWheel(e) {
    if (!wrap) return;
    e.preventDefault();
    const factor = Math.exp(-e.deltaY * 0.0015);
    zoomBy(factor, e.clientX, e.clientY);
  }

  function touchDistance(t1, t2) {
    const dx = t1.clientX - t2.clientX;
    const dy = t1.clientY - t2.clientY;
    return Math.hypot(dx, dy);
  }

  function touchMidpoint(t1, t2) {
    return {
      x: (t1.clientX + t2.clientX) / 2,
      y: (t1.clientY + t2.clientY) / 2,
    };
  }

  function startTouch(e) {
    if (!wrap) return;
    if (e.touches.length === 1) {
      const t = e.touches[0];
      isDragging = true;
      hasDragged = false;
      dragStart.x = t.clientX;
      dragStart.y = t.clientY;
      lastPan.x = panX;
      lastPan.y = panY;
      canvas.classList.add('is-dragging');
    } else if (e.touches.length === 2) {
      isDragging = false;
      const [t1, t2] = [e.touches[0], e.touches[1]];
      pinchStartDistance = touchDistance(t1, t2);
      pinchStartScale = scale;
      pinchStartMid = touchMidpoint(t1, t2);
      pinchStartPan.x = panX;
      pinchStartPan.y = panY;
      canvas.classList.add('is-dragging');
    }
  }

  function onTouchMove(e) {
    if (!wrap) return;
    if (e.touches.length === 1 && isDragging) {
      const t = e.touches[0];
      const dx = t.clientX - dragStart.x;
      const dy = t.clientY - dragStart.y;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) hasDragged = true;
      panX = lastPan.x + dx;
      panY = lastPan.y + dy;
      updateTransform();
    } else if (e.touches.length === 2) {
      e.preventDefault();
      const [t1, t2] = [e.touches[0], e.touches[1]];
      const d = touchDistance(t1, t2);
      const mid = touchMidpoint(t1, t2);
      const newScale = clamp(pinchStartScale * (d / pinchStartDistance), minScale, maxScale);
      const { x: cx, y: cy, rect } = getWrapCentre();
      const midOffsetStartX = pinchStartMid.x - rect.left - cx;
      const midOffsetStartY = pinchStartMid.y - rect.top - cy;
      const midOffsetX = mid.x - rect.left - cx;
      const midOffsetY = mid.y - rect.top - cy;
      const scaleRatio = newScale / pinchStartScale;
      panX = pinchStartPan.x * scaleRatio + midOffsetX - midOffsetStartX * scaleRatio;
      panY = pinchStartPan.y * scaleRatio + midOffsetY - midOffsetStartY * scaleRatio;
      scale = newScale;
      updateTransform();
    }
  }

  function endTouch() {
    isDragging = false;
    canvas.classList.remove('is-dragging');
  }

  // -------------------------------------------------------------------------
  // Controls
  // -------------------------------------------------------------------------

  function expandAll() {
    people.forEach((p) => expandedNodes.add(p.id));
    renderTree();
    showToast('All relatives revealed');
  }

  function collapseToRoot() {
    expandedNodes = new Set(root_id ? [root_id] : []);
    renderTree();
    showToast('Collapsed to root only');
  }

  function expandToGen(targetGen) {
    expandedNodes = new Set(root_id ? [root_id] : []);
    people.forEach((p) => {
      if (p.generation >= targetGen && p.generation <= 0) {
        expandedNodes.add(p.id);
      }
    });
    renderTree();
  }

  function showToast(text) {
    const toast = document.getElementById('toast');
    const toastText = document.getElementById('toastText');
    if (!toast || !toastText) return;
    toastText.textContent = text;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 2500);
  }

  // -------------------------------------------------------------------------
  // Create sheet
  // -------------------------------------------------------------------------

  const createSheet = document.getElementById('tree-create-sheet');
  const createSheetBackdrop = document.getElementById('tree-sheet-backdrop');
  let activeCreateTrigger = null;

  function openCreateSheet(trigger) {
    if (!createSheet || !createSheetBackdrop) return;
    activeCreateTrigger = trigger;
    createSheet.classList.add('is-open');
    createSheetBackdrop.classList.add('is-open');
    createSheet.setAttribute('aria-hidden', 'false');
    document.body.classList.add('is-tree-modal-open');
    const closeBtn = createSheet.querySelector('[data-create-sheet-close]');
    if (closeBtn) setTimeout(() => closeBtn.focus({ preventScroll: true }), 80);
  }

  function closeCreateSheet() {
    if (!createSheet || !createSheetBackdrop) return;
    createSheet.classList.remove('is-open');
    createSheetBackdrop.classList.remove('is-open');
    createSheet.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('is-tree-modal-open');
    if (activeCreateTrigger) {
      activeCreateTrigger.focus({ preventScroll: true });
      activeCreateTrigger = null;
    }
  }

  // -------------------------------------------------------------------------
  // Detail panel
  // -------------------------------------------------------------------------

  function renderRelativeChip(relativeId) {
    const relative = peopleMap.get(relativeId);
    if (!relative) return null;

    const chip = document.createElement('button');
    chip.className = 'detail-relative';
    chip.type = 'button';

    const avatar = document.createElement('span');
    avatar.className = 'detail-relative-avatar';
    if (relative.avatar_url) {
      const img = document.createElement('img');
      img.src = relative.avatar_url;
      img.alt = '';
      img.onerror = function () {
        avatar.textContent = relative.initials;
      };
      avatar.appendChild(img);
    } else {
      avatar.textContent = relative.initials;
    }
    chip.appendChild(avatar);

    const name = document.createElement('span');
    name.textContent = relative.name;
    chip.appendChild(name);

    chip.addEventListener('click', (e) => {
      e.stopPropagation();
      openDetail(relativeId);
    });

    return chip;
  }

  function populateRelatives(containerId, relativeIds) {
    const container = document.getElementById(containerId);
    const section = container ? container.closest('.detail-section') : null;
    if (!container) return;

    container.innerHTML = '';
    const chips = relativeIds
      .map((id) => renderRelativeChip(id))
      .filter(Boolean);

    if (chips.length === 0) {
      if (section) section.style.display = 'none';
      return;
    }

    if (section) section.style.display = '';
    chips.forEach((chip) => container.appendChild(chip));
  }

  function getCsrfToken() {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function setVisible(el, visible) {
    if (!el) return;
    el.style.display = visible ? '' : 'none';
  }

  function setDetailStatus(person) {
    const statusEl = document.getElementById('detail-status');
    if (!statusEl) return;
    statusEl.innerHTML = '';

    if (person.claimed_by_me) {
      statusEl.textContent = 'Connected to your account';
      statusEl.className = 'detail-status is-claimed';
    } else if (person.is_claimed && person.claimed_by) {
      statusEl.textContent = `Claimed by ${person.claimed_by}`;
      statusEl.className = 'detail-status is-claimed';
    } else {
      statusEl.textContent = 'Not connected to a user account';
      statusEl.className = 'detail-status is-unclaimed';
    }
  }

  function setDetailToolbar(person) {
    const editBtn = document.getElementById('detail-action-edit');
    const inviteBtn = document.getElementById('detail-action-invite');
    const anchorBtn = document.getElementById('detail-action-anchor');
    const descendantsBtn = document.getElementById('detail-action-descendants');
    const storyLink = document.getElementById('detail-action-story');
    const addRelativeWrap = document.getElementById('detail-action-add-relative');

    setVisible(editBtn, person.can_edit);
    setVisible(inviteBtn, person.can_invite);
    setVisible(anchorBtn, person.can_set_anchor);
    setVisible(descendantsBtn, true);
    setVisible(storyLink, true);
    setVisible(addRelativeWrap, person.can_edit);

    if (editBtn) editBtn.dataset.url = person.urls.edit_name;
    if (inviteBtn) inviteBtn.dataset.url = person.urls.invite;
    if (anchorBtn) anchorBtn.dataset.url = person.urls.set_anchor;
    if (descendantsBtn) descendantsBtn.dataset.url = person.urls.descendants;
    if (storyLink) storyLink.href = person.urls.story_create;

    ['parent', 'child', 'partner', 'sibling'].forEach((rel) => {
      const btn = document.querySelector(`[data-detail-action="add_${rel}"]`);
      if (btn && person.urls.add_relative) {
        btn.dataset.url = person.urls.add_relative[rel];
      }
    });
  }

  function setDetailBio(person) {
    const section = document.getElementById('detail-about-section');
    const bioEl = document.getElementById('detail-bio');
    if (!section || !bioEl) return;
    if (person.biography) {
      bioEl.textContent = person.biography;
      setVisible(section, true);
    } else {
      setVisible(section, false);
    }
  }

  function setDetailContent(person) {
    const section = document.getElementById('detail-content-section');
    const statsEl = document.getElementById('detail-content-stats');
    if (!section || !statsEl) return;

    const hasMemories = person.memory_count > 0;
    const hasStories = person.story_count > 0;
    if (!hasMemories && !hasStories) {
      setVisible(section, false);
      return;
    }

    setVisible(section, true);
    statsEl.innerHTML = '';

    if (hasMemories) {
      const memory = document.createElement('a');
      memory.className = 'detail-content-stat';
      memory.href = '/memories/';
      memory.innerHTML = `<strong>${person.memory_count}</strong> <span>Memory${person.memory_count === 1 ? '' : 'ies'}</span>`;
      statsEl.appendChild(memory);
    }

    if (hasStories) {
      const story = document.createElement('a');
      story.className = 'detail-content-stat';
      story.href = '/stories/';
      story.innerHTML = `<strong>${person.story_count}</strong> <span>Story${person.story_count === 1 ? '' : 'ies'}</span>`;
      statsEl.appendChild(story);
    }
  }

  function openDetail(personId) {
    const person = peopleMap.get(personId);
    if (!person) return;

    const nameEl = document.getElementById('detail-name');
    const roleEl = document.getElementById('detail-role');
    const bornEl = document.getElementById('detail-born');
    const locationEl = document.getElementById('detail-location');
    const genderEl = document.getElementById('detail-gender');
    const avatarEl = document.getElementById('detail-avatar');
    const profileLink = document.getElementById('detail-profile-link');

    if (nameEl) nameEl.textContent = person.name;
    if (roleEl) roleEl.textContent = person.role;
    if (bornEl) bornEl.textContent = person.born || 'Not recorded';
    if (locationEl) locationEl.textContent = person.location || 'Not recorded';
    if (genderEl)
      genderEl.textContent =
        person.gender.charAt(0).toUpperCase() + person.gender.slice(1);

    if (avatarEl) {
      avatarEl.innerHTML = '';
      if (person.avatar_url) {
        const img = document.createElement('img');
        img.src = person.avatar_url;
        img.alt = '';
        img.onerror = function () {
          avatarEl.textContent = person.initials;
        };
        avatarEl.appendChild(img);
      } else {
        avatarEl.textContent = person.initials;
      }
    }

    if (profileLink) {
      profileLink.href = person.urls.drawer;
    }

    setDetailStatus(person);
    setDetailToolbar(person);
    setDetailBio(person);
    setDetailContent(person);

    populateRelatives(
      'detail-parents',
      [person.father_id, person.mother_id].filter(Boolean)
    );
    populateRelatives(
      'detail-partner',
      person.partner_id ? [person.partner_id] : []
    );
    populateRelatives('detail-siblings', person.sibling_ids);
    populateRelatives('detail-children', person.child_ids);

    detailOverlay.classList.add('is-open');
    detailPanel.classList.add('is-open');

    if (typeof lucide !== 'undefined') {
      lucide.createIcons();
    }
  }

  function closeDetail() {
    detailOverlay.classList.remove('is-open');
    detailPanel.classList.remove('is-open');
  }

  // -------------------------------------------------------------------------
  // Event binding
  // -------------------------------------------------------------------------

  document.addEventListener('click', (e) => {
    const target = e.target;
    if (target.closest('[data-tree-expand-all]')) {
      expandAll();
      return;
    }
    if (target.closest('[data-tree-collapse]')) {
      collapseToRoot();
      return;
    }
    if (target.closest('[data-tree-reset]')) {
      resetView();
      return;
    }
    if (target.closest('[data-zoom-in]')) {
      zoomBy(1.2);
      return;
    }
    if (target.closest('[data-zoom-out]')) {
      zoomBy(0.8);
      return;
    }
    if (target.closest('[data-zoom-fit]')) {
      fitToScreen();
      return;
    }
    if (target.closest('[data-detail-close]')) {
      closeDetail();
      return;
    }
    if (target.closest('.detail-overlay.is-open')) {
      closeDetail();
      return;
    }
    const detailAction = target.closest('[data-detail-action]');
    if (detailAction) {
      const action = detailAction.dataset.detailAction;
      const url = detailAction.dataset.url;
      if (action === 'anchor' && url) {
        fetch(url, { method: 'POST', headers: { 'X-CSRFToken': getCsrfToken() } })
          .then((res) => {
            if (res.ok) {
              showToast('Anchor updated');
              window.location.reload();
            } else {
              showToast('Could not update anchor');
            }
          })
          .catch(() => showToast('Could not update anchor'));
      } else if (url) {
        window.location.href = url;
      }
      return;
    }
    const menuToggle = target.closest('[data-detail-menu-toggle]');
    if (menuToggle) {
      const menu = menuToggle.closest('.detail-tool.has-menu');
      if (menu) menu.classList.toggle('is-open');
      return;
    }
    if (!target.closest('.detail-tool.has-menu')) {
      document.querySelectorAll('.detail-tool.has-menu.is-open').forEach((m) => m.classList.remove('is-open'));
    }
    if (target.closest('[data-create-sheet-trigger]')) {
      openCreateSheet(target.closest('[data-create-sheet-trigger]'));
      return;
    }
    if (target.closest('[data-create-sheet-close]')) {
      closeCreateSheet();
      return;
    }
    if (target.closest('[data-tree-toast]')) {
      const message = target.closest('[data-tree-toast]').dataset.treeToast;
      if (message) showToast(message);
      return;
    }
    if (createSheetBackdrop && createSheetBackdrop.classList.contains('is-open')) {
      closeCreateSheet();
    }
  });

  if (wrap) {
    wrap.addEventListener('mousedown', startDrag);
    wrap.addEventListener('wheel', onWheel, { passive: false });
    wrap.addEventListener('touchstart', startTouch, { passive: false });
  }
  window.addEventListener('mousemove', onDrag);
  window.addEventListener('mouseup', endDrag);
  window.addEventListener('touchmove', onTouchMove, { passive: false });
  window.addEventListener('touchend', endTouch);
  window.addEventListener('touchcancel', endTouch);

  window.addEventListener('resize', () => {
    centerCanvas();
    renderTree();
  });

  document.body.addEventListener('htmx:afterSwap', (event) => {
    if (
      event.detail &&
      event.detail.target &&
      event.detail.target.id === 'tree-create-sheet'
    ) {
      const closeBtn = createSheet.querySelector('[data-create-sheet-close]');
      if (closeBtn) closeBtn.focus({ preventScroll: true });
    }
  });

  // -------------------------------------------------------------------------
  // Init
  // -------------------------------------------------------------------------

  centerCanvas();
  renderTree();
})();
