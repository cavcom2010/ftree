(function () {
  'use strict';

  const TAP_MOVE_THRESHOLD = 18;
  let peopleMap = new Map();
  let tapStart = null;
  let lastOpened = { id: null, at: 0 };

  function isTreePage() {
    return Boolean(document.querySelector('[data-tree-page]') && window.TREE_DATA);
  }

  function hydratePeopleMap() {
    const data = window.TREE_DATA || {};
    peopleMap = new Map();
    (data.people || []).forEach((person) => {
      if (!person || person.id === undefined || person.id === null) return;
      peopleMap.set(String(person.id), person);
    });
  }

  function personById(personId) {
    return peopleMap.get(String(personId || '')) || null;
  }

  function safeText(value, fallback) {
    if (value === undefined || value === null || value === '') return fallback || '';
    return String(value);
  }

  function setText(id, value, fallback) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = safeText(value, fallback);
  }

  function setVisible(el, isVisible) {
    if (!el) return;
    el.style.display = isVisible ? '' : 'none';
  }

  function formatTitle(value) {
    const text = safeText(value, '').replace(/_/g, ' ').trim();
    if (!text) return 'Not recorded';
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  function getUrl(person, key) {
    return person && person.urls ? person.urls[key] || '' : '';
  }

  function getAddRelativeUrls(person) {
    return (person && person.urls && person.urls.add_relative) ? person.urls.add_relative : {};
  }

  function renderAvatar(el, person) {
    if (!el || !person) return;
    el.innerHTML = '';
    if (person.avatar_url) {
      const img = document.createElement('img');
      img.src = person.avatar_url;
      img.alt = '';
      img.onerror = function () {
        el.textContent = safeText(person.initials, '?');
      };
      el.appendChild(img);
    } else {
      el.textContent = safeText(person.initials, '?');
    }
  }

  function ensureQuickRelativesBlock() {
    if (document.getElementById('tree-quick-relatives')) return;
    const status = document.getElementById('detail-status');
    if (!status || !status.parentElement) return;

    const block = document.createElement('section');
    block.className = 'tree-quick-relatives';
    block.id = 'tree-quick-relatives';
    block.hidden = true;
    block.setAttribute('aria-labelledby', 'tree-quick-relatives-title');
    block.innerHTML = [
      '<h3 id="tree-quick-relatives-title">Add relatives</h3>',
      '<div class="tree-quick-actions" aria-label="Add relatives">',
      '  <button type="button" data-detail-action="add_parent"><i data-lucide="user-plus"></i><span>Parent</span></button>',
      '  <button type="button" data-detail-action="add_partner"><i data-lucide="heart-handshake"></i><span>Partner</span></button>',
      '  <button type="button" data-detail-action="add_child"><i data-lucide="baby"></i><span>Child</span></button>',
      '  <button type="button" data-detail-action="add_sibling"><i data-lucide="users"></i><span>Sibling</span></button>',
      '</div>',
      '<div class="tree-quick-helper">',
      '  <p><strong>Grandparents:</strong> open your parent\'s card and add their parents.</p>',
      '  <p><strong>Aunties/uncles:</strong> open your parent\'s card and add their siblings.</p>',
      '</div>',
    ].join('');

    status.insertAdjacentElement('afterend', block);
  }

  function setDetailStatus(person) {
    const statusEl = document.getElementById('detail-status');
    if (!statusEl) return;

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
    const deleteBtn = document.getElementById('detail-action-delete');
    const quickRelatives = document.getElementById('tree-quick-relatives');
    const quickTitle = document.getElementById('tree-quick-relatives-title');

    setVisible(editBtn, Boolean(person.can_edit));
    setVisible(inviteBtn, Boolean(person.can_invite));
    setVisible(anchorBtn, Boolean(person.can_set_anchor));
    setVisible(descendantsBtn, Boolean(person.child_ids && person.child_ids.length > 0));
    setVisible(storyLink, true);
    setVisible(addRelativeWrap, false);
    setVisible(deleteBtn, Boolean(person.can_delete));

    if (editBtn) editBtn.dataset.url = getUrl(person, 'edit_name');
    if (inviteBtn) inviteBtn.dataset.url = getUrl(person, 'invite');
    if (anchorBtn) anchorBtn.dataset.url = getUrl(person, 'set_anchor');
    if (descendantsBtn) descendantsBtn.dataset.url = getUrl(person, 'descendants');
    if (storyLink) storyLink.href = getUrl(person, 'story_create') || '#';
    if (deleteBtn) deleteBtn.dataset.url = getUrl(person, 'delete');

    const addUrls = getAddRelativeUrls(person);
    const canAdd = Boolean(person.can_add_relative && addUrls && Object.keys(addUrls).length);
    if (quickRelatives) {
      quickRelatives.hidden = !canAdd;
      setVisible(quickRelatives, canAdd);
    }
    if (quickTitle) {
      quickTitle.textContent = `Add relatives for ${safeText(person.name, 'this person')}`;
    }

    ['parent', 'partner', 'child', 'sibling'].forEach((relation) => {
      document.querySelectorAll(`[data-detail-action="add_${relation}"]`).forEach((button) => {
        if (addUrls && addUrls[relation]) {
          button.dataset.url = addUrls[relation];
          button.disabled = false;
          button.removeAttribute('aria-disabled');
        } else {
          delete button.dataset.url;
          button.disabled = true;
          button.setAttribute('aria-disabled', 'true');
        }
      });
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
      bioEl.textContent = '';
      setVisible(section, false);
    }
  }

  function setDetailContent(person) {
    const section = document.getElementById('detail-content-section');
    const statsEl = document.getElementById('detail-content-stats');
    if (!section || !statsEl) return;

    const memoryCount = Number(person.memory_count || 0);
    const storyCount = Number(person.story_count || 0);
    if (!memoryCount && !storyCount) {
      statsEl.innerHTML = '';
      setVisible(section, false);
      return;
    }

    setVisible(section, true);
    statsEl.innerHTML = '';

    if (memoryCount) {
      const memory = document.createElement('a');
      memory.className = 'detail-content-stat';
      memory.href = '/memories/';
      memory.innerHTML = `<strong>${memoryCount}</strong> <span>Memory${memoryCount === 1 ? '' : 'ies'}</span>`;
      statsEl.appendChild(memory);
    }

    if (storyCount) {
      const story = document.createElement('a');
      story.className = 'detail-content-stat';
      story.href = '/stories/';
      story.innerHTML = `<strong>${storyCount}</strong> <span>Story${storyCount === 1 ? '' : 'ies'}</span>`;
      statsEl.appendChild(story);
    }
  }

  function appendSocialRow(container, label, value) {
    if (!value) return;
    const row = document.createElement('div');
    row.className = 'detail-social-row';
    const labelEl = document.createElement('span');
    labelEl.textContent = label;
    const valueEl = document.createElement('strong');
    valueEl.textContent = value;
    row.appendChild(labelEl);
    row.appendChild(valueEl);
    container.appendChild(row);
  }

  function setDetailSocial(person) {
    const section = document.getElementById('detail-social-section');
    const container = document.getElementById('detail-social');
    if (!section || !container) return;

    const social = person.social || {};
    const recentActivity = social.recent_activity || [];
    const hasSocial = Boolean(
      social.connected_label ||
      social.pending_invite_label ||
      social.story_count > 0 ||
      social.memory_count > 0 ||
      recentActivity.length > 0
    );

    if (!hasSocial) {
      container.innerHTML = '';
      setVisible(section, false);
      return;
    }

    setVisible(section, true);
    container.innerHTML = '';
    appendSocialRow(container, 'Connected account', social.connected_label);
    appendSocialRow(container, 'Pending invite', social.pending_invite_label);

    const stats = document.createElement('div');
    stats.className = 'detail-social-stats';
    if (social.story_count > 0) {
      const story = document.createElement('span');
      story.textContent = `${social.story_count} tagged ${social.story_count === 1 ? 'story' : 'stories'}`;
      stats.appendChild(story);
    }
    if (social.memory_count > 0) {
      const memory = document.createElement('span');
      memory.textContent = `${social.memory_count} tagged ${social.memory_count === 1 ? 'memory' : 'memories'}`;
      stats.appendChild(memory);
    }
    if (stats.children.length) container.appendChild(stats);

    if (recentActivity.length) {
      const list = document.createElement('div');
      list.className = 'detail-social-activity';
      recentActivity.forEach((item) => {
        const activity = document.createElement('div');
        const message = document.createElement('strong');
        message.textContent = item.message || '';
        const date = document.createElement('span');
        date.textContent = item.date || '';
        activity.appendChild(message);
        activity.appendChild(date);
        list.appendChild(activity);
      });
      container.appendChild(list);
    }
  }

  function renderRelativeChip(relativeId) {
    const relative = personById(relativeId);
    if (!relative) return null;

    const chip = document.createElement('button');
    chip.className = 'detail-relative';
    chip.type = 'button';
    chip.dataset.detailPersonId = String(relative.id);

    const avatar = document.createElement('span');
    avatar.className = 'detail-relative-avatar';
    if (relative.avatar_url) {
      const img = document.createElement('img');
      img.src = relative.avatar_url;
      img.alt = '';
      img.onerror = function () {
        avatar.textContent = safeText(relative.initials, '?');
      };
      avatar.appendChild(img);
    } else {
      avatar.textContent = safeText(relative.initials, '?');
    }
    chip.appendChild(avatar);

    const name = document.createElement('span');
    name.textContent = safeText(relative.name, 'Relative');
    chip.appendChild(name);

    chip.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      openPersonDetail(relative.id);
    });

    return chip;
  }

  function populateRelatives(containerId, relativeIds) {
    const container = document.getElementById(containerId);
    const section = container ? container.closest('.detail-section') : null;
    if (!container) return;

    container.innerHTML = '';
    const chips = (relativeIds || [])
      .filter((id) => id && String(id) !== 'null')
      .map((id) => renderRelativeChip(id))
      .filter(Boolean);

    if (!chips.length) {
      if (section) setVisible(section, false);
      return;
    }

    if (section) setVisible(section, true);
    chips.forEach((chip) => container.appendChild(chip));
  }

  function markFocusedNode(personId) {
    document.querySelectorAll('.person-node.is-focused').forEach((node) => {
      node.classList.remove('is-focused');
    });
    const node = document.querySelector(`.person-node[data-person-id="${String(personId).replace(/"/g, '\\"')}"]`);
    if (node) node.classList.add('is-focused');
  }

  function openPersonDetail(personId) {
    const person = personById(personId);
    const detailOverlay = document.getElementById('detail-overlay');
    const detailPanel = document.getElementById('detail-panel');
    if (!person || !detailOverlay || !detailPanel) return false;

    ensureQuickRelativesBlock();

    setText('detail-name', person.name, 'Family member');
    setText('detail-role', person.role, 'Relative');
    setText('detail-born', person.born, 'Not recorded');
    setText('detail-location', person.location, 'Not recorded');
    setText('detail-gender', formatTitle(person.gender), 'Not recorded');

    const lifeStatusRow = document.getElementById('detail-life-status-row');
    const lifeStatusEl = document.getElementById('detail-life-status');
    if (lifeStatusRow && lifeStatusEl) {
      lifeStatusEl.textContent = safeText(person.life_status, '');
      setVisible(lifeStatusRow, Boolean(person.life_status));
    }

    renderAvatar(document.getElementById('detail-avatar'), person);

    const profileLink = document.getElementById('detail-profile-link');
    if (profileLink) profileLink.href = getUrl(person, 'drawer') || '#';

    setDetailStatus(person);
    setDetailToolbar(person);
    setDetailBio(person);
    setDetailContent(person);
    setDetailSocial(person);

    populateRelatives('detail-parents', [person.father_id, person.mother_id]);
    populateRelatives('detail-partner', person.partner_id ? [person.partner_id] : []);
    populateRelatives('detail-siblings', person.sibling_ids || []);
    populateRelatives('detail-children', person.child_ids || []);

    detailOverlay.classList.add('is-open');
    detailPanel.classList.add('is-open');
    document.body.classList.add('is-tree-modal-open');
    detailPanel.scrollTop = 0;
    markFocusedNode(person.id);

    lastOpened = { id: String(person.id), at: Date.now() };

    if (typeof lucide !== 'undefined') {
      lucide.createIcons();
    }

    const closeBtn = detailPanel.querySelector('[data-detail-close]');
    if (closeBtn) {
      window.setTimeout(() => closeBtn.focus({ preventScroll: true }), 50);
    }

    return true;
  }

  function getNodeFromEvent(event) {
    const target = event.target;
    if (!(target instanceof Element)) return null;
    return target.closest('.person-node[data-person-id]');
  }

  function shouldIgnoreRecentOpen(personId) {
    return lastOpened.id === String(personId) && Date.now() - lastOpened.at < 550;
  }

  function stopEvent(event) {
    event.preventDefault();
    event.stopPropagation();
    if (typeof event.stopImmediatePropagation === 'function') {
      event.stopImmediatePropagation();
    }
  }

  function openFromNode(node, event) {
    if (!node || !node.dataset.personId) return false;
    const opened = openPersonDetail(node.dataset.personId);
    if (opened && event) stopEvent(event);
    return opened;
  }

  function handleRootConnect(event) {
    const target = event.target;
    if (!(target instanceof Element)) return false;
    const trigger = target.closest('[data-tree-open-root-detail]');
    if (!trigger) return false;
    const rootId = window.TREE_DATA && window.TREE_DATA.root_id;
    if (!rootId) return false;
    const opened = openPersonDetail(rootId);
    if (opened) stopEvent(event);
    return opened;
  }

  function bindReliableCardOpening() {
    document.addEventListener('click', (event) => {
      if (handleRootConnect(event)) return;

      const node = getNodeFromEvent(event);
      if (!node) return;
      if (shouldIgnoreRecentOpen(node.dataset.personId)) {
        stopEvent(event);
        return;
      }
      openFromNode(node, event);
    }, true);

    document.addEventListener('pointerdown', (event) => {
      const node = getNodeFromEvent(event);
      if (!node || event.pointerType === 'mouse') return;
      tapStart = {
        id: node.dataset.personId,
        pointerId: event.pointerId,
        x: event.clientX,
        y: event.clientY,
      };
      event.stopPropagation();
      if (typeof event.stopImmediatePropagation === 'function') event.stopImmediatePropagation();
    }, true);

    document.addEventListener('pointerup', (event) => {
      if (!tapStart || tapStart.pointerId !== event.pointerId) return;
      const node = getNodeFromEvent(event);
      const dx = event.clientX - tapStart.x;
      const dy = event.clientY - tapStart.y;
      const isTap = Math.hypot(dx, dy) <= TAP_MOVE_THRESHOLD;
      const startId = tapStart.id;
      tapStart = null;
      if (!isTap || !node || String(node.dataset.personId) !== String(startId)) return;
      openFromNode(node, event);
    }, true);

    document.addEventListener('touchstart', (event) => {
      const node = getNodeFromEvent(event);
      if (!node || !event.touches || event.touches.length !== 1) return;
      const touch = event.touches[0];
      tapStart = {
        id: node.dataset.personId,
        touchId: touch.identifier,
        x: touch.clientX,
        y: touch.clientY,
      };
      event.stopPropagation();
      if (typeof event.stopImmediatePropagation === 'function') event.stopImmediatePropagation();
    }, { capture: true, passive: true });

    document.addEventListener('touchmove', (event) => {
      if (!tapStart || !event.touches) return;
      const touch = Array.from(event.touches).find((item) => item.identifier === tapStart.touchId);
      if (!touch) return;
      const dx = touch.clientX - tapStart.x;
      const dy = touch.clientY - tapStart.y;
      if (Math.hypot(dx, dy) > TAP_MOVE_THRESHOLD) {
        tapStart.moved = true;
      }
      event.stopPropagation();
      if (typeof event.stopImmediatePropagation === 'function') event.stopImmediatePropagation();
    }, { capture: true, passive: true });

    document.addEventListener('touchend', (event) => {
      if (!tapStart || !event.changedTouches) return;
      const touch = Array.from(event.changedTouches).find((item) => item.identifier === tapStart.touchId);
      if (!touch) return;
      const node = getNodeFromEvent(event);
      const dx = touch.clientX - tapStart.x;
      const dy = touch.clientY - tapStart.y;
      const isTap = !tapStart.moved && Math.hypot(dx, dy) <= TAP_MOVE_THRESHOLD;
      const startId = tapStart.id;
      tapStart = null;
      if (!isTap || !node || String(node.dataset.personId) !== String(startId)) return;
      openFromNode(node, event);
    }, { capture: true, passive: false });

    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const node = getNodeFromEvent(event);
      if (!node) return;
      openFromNode(node, event);
    }, true);
  }

  function enhanceNodes() {
    document.querySelectorAll('.person-node[data-person-id]').forEach((node) => {
      if (!node.hasAttribute('tabindex')) node.setAttribute('tabindex', '0');
      if (!node.hasAttribute('role')) node.setAttribute('role', 'button');
      const person = personById(node.dataset.personId);
      if (person && !node.getAttribute('aria-label')) {
        node.setAttribute('aria-label', `Open details for ${safeText(person.name, 'this person')}`);
      }
    });
  }

  function observeNodes() {
    const nodesContainer = document.getElementById('nodes-container');
    if (!nodesContainer || typeof MutationObserver === 'undefined') return;
    const observer = new MutationObserver(() => enhanceNodes());
    observer.observe(nodesContainer, { childList: true, subtree: true });
    enhanceNodes();
  }

  function init() {
    if (!isTreePage()) return;
    hydratePeopleMap();
    ensureQuickRelativesBlock();
    bindReliableCardOpening();
    observeNodes();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
