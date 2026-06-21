(function () {
  'use strict';

  const TREE_DATA = window.TREE_DATA || { people: [], root_id: null };
  const people = Array.isArray(TREE_DATA.people) ? TREE_DATA.people : [];
  const rootId = TREE_DATA.root_id ? String(TREE_DATA.root_id) : null;
  const touchQuery = window.matchMedia('(hover: none) and (pointer: coarse)');
  const peopleMap = new Map();
  let revealedId = null;

  people.forEach((person) => {
    person.id = String(person.id);
    if (person.father_id) person.father_id = String(person.father_id);
    if (person.mother_id) person.mother_id = String(person.mother_id);
    if (person.partner_id) person.partner_id = String(person.partner_id);
    person.sibling_ids = (person.sibling_ids || []).map(String);
    person.child_ids = (person.child_ids || []).map(String);
    peopleMap.set(person.id, person);
  });

  function isTouchMode() {
    return touchQuery.matches;
  }

  function getPersonRole(person) {
    if (!person) return '';
    if (person.id === rootId) return 'You · Gen 0';
    return person.role || `Generation ${person.generation || 0}`;
  }

  function makePill(text) {
    const pill = document.createElement('span');
    pill.textContent = text;
    return pill;
  }

  function getRevealPills(person) {
    if (!person) return [];
    const pills = [`Gen ${person.generation || 0}`];
    const parentCount = [person.father_id, person.mother_id].filter(Boolean).length;
    const childCount = person.child_ids.length;
    const siblingCount = person.sibling_ids.length;

    if (person.life_status) pills.push(person.life_status);
    if (parentCount) pills.push(`${parentCount} parent${parentCount === 1 ? '' : 's'}`);
    if (childCount) pills.push(`${childCount} child${childCount === 1 ? '' : 'ren'}`);
    if (siblingCount) pills.push(`${siblingCount} sibling${siblingCount === 1 ? '' : 's'}`);
    if (person.partner_id) pills.push('Partner linked');

    return pills.slice(0, 5);
  }

  function ensureRevealPanel(node, person) {
    let panel = node.querySelector('.mobile-touch-reveal');
    if (panel) return panel;

    panel = document.createElement('div');
    panel.className = 'mobile-touch-reveal';
    panel.setAttribute('aria-hidden', 'true');

    const title = document.createElement('strong');
    title.className = 'mobile-touch-reveal__title';
    title.textContent = person.name || 'Unnamed person';
    panel.appendChild(title);

    const pills = document.createElement('div');
    pills.className = 'mobile-touch-reveal__pills';
    getRevealPills(person).forEach((pillText) => pills.appendChild(makePill(pillText)));
    panel.appendChild(pills);

    const hint = document.createElement('p');
    hint.className = 'mobile-touch-reveal__hint';
    hint.textContent = 'Tap again to open profile';
    panel.appendChild(hint);

    node.appendChild(panel);
    return panel;
  }

  function clearReveal() {
    if (!revealedId) return;
    const previous = document.querySelector(`.person-node[data-person-id="${cssEscape(revealedId)}"]`);
    if (previous) {
      previous.classList.remove('is-touch-revealed');
      const panel = previous.querySelector('.mobile-touch-reveal');
      if (panel) panel.setAttribute('aria-hidden', 'true');
    }
    revealedId = null;
  }

  function revealNode(node, person) {
    clearReveal();
    ensureRevealPanel(node, person);
    node.classList.add('is-touch-revealed');
    const panel = node.querySelector('.mobile-touch-reveal');
    if (panel) panel.setAttribute('aria-hidden', 'false');
    revealedId = person.id;
  }

  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === 'function') {
      return window.CSS.escape(value);
    }
    return String(value).replace(/"/g, '\\"');
  }

  function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text || '';
  }

  function setVisible(el, visible) {
    if (el) el.style.display = visible ? '' : 'none';
  }

  function getCsrfToken() {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

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
        avatar.textContent = relative.initials || '?';
      };
      avatar.appendChild(img);
    } else {
      avatar.textContent = relative.initials || '?';
    }
    chip.appendChild(avatar);

    const name = document.createElement('span');
    name.textContent = relative.name || 'Unnamed person';
    chip.appendChild(name);

    chip.addEventListener('click', (event) => {
      event.stopPropagation();
      openTouchDetail(relative.id);
    });

    return chip;
  }

  function populateRelatives(containerId, relativeIds) {
    const container = document.getElementById(containerId);
    const section = container ? container.closest('.detail-section') : null;
    if (!container) return;

    container.innerHTML = '';
    const chips = relativeIds.map(renderRelativeChip).filter(Boolean);
    setVisible(section, chips.length > 0);
    chips.forEach((chip) => container.appendChild(chip));
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
    const urls = person.urls || {};

    setVisible(editBtn, Boolean(person.can_edit));
    setVisible(inviteBtn, Boolean(person.can_invite));
    setVisible(anchorBtn, Boolean(person.can_set_anchor));
    setVisible(descendantsBtn, person.child_ids && person.child_ids.length > 0);
    setVisible(storyLink, true);
    setVisible(addRelativeWrap, Boolean(person.can_add_relative));
    setVisible(deleteBtn, Boolean(person.can_delete));

    if (editBtn) editBtn.dataset.url = urls.edit_name || '';
    if (inviteBtn) inviteBtn.dataset.url = urls.invite || '';
    if (anchorBtn) anchorBtn.dataset.url = urls.set_anchor || '';
    if (descendantsBtn) descendantsBtn.dataset.url = urls.descendants || '';
    if (storyLink) storyLink.href = urls.story_create || '#';
    if (deleteBtn) deleteBtn.dataset.url = urls.delete || '';

    const addRelativeUrls = urls.add_relative || {};
    ['parent', 'child', 'partner', 'sibling'].forEach((rel) => {
      const btn = document.querySelector(`[data-detail-action="add_${rel}"]`);
      if (btn) btn.dataset.url = addRelativeUrls[rel] || '';
    });

    const picker = document.getElementById('detail-relation-picker');
    const toggle = document.querySelector('[data-detail-menu-toggle]');
    const wrap = document.getElementById('detail-action-add-relative');
    if (picker) picker.hidden = true;
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
    if (wrap) wrap.classList.remove('is-open');
  }

  function setDetailBio(person) {
    const section = document.getElementById('detail-about-section');
    const bioEl = document.getElementById('detail-bio');
    if (!section || !bioEl) return;
    bioEl.textContent = person.biography || '';
    setVisible(section, Boolean(person.biography));
  }

  function openTouchDetail(personId) {
    const person = peopleMap.get(String(personId));
    const overlay = document.getElementById('detail-overlay');
    const panel = document.getElementById('detail-panel');
    if (!person || !overlay || !panel) return;

    setText('detail-name', person.name || 'Unnamed person');
    setText('detail-role', getPersonRole(person));
    setText('detail-born', person.born || 'Not recorded');
    setText('detail-location', person.location || 'Not recorded');
    setText('detail-gender', person.gender ? person.gender.charAt(0).toUpperCase() + person.gender.slice(1) : 'Not recorded');

    const lifeStatusRow = document.getElementById('detail-life-status-row');
    setText('detail-life-status', person.life_status || '');
    setVisible(lifeStatusRow, Boolean(person.life_status));

    const avatarEl = document.getElementById('detail-avatar');
    if (avatarEl) {
      avatarEl.innerHTML = '';
      if (person.avatar_url) {
        const img = document.createElement('img');
        img.src = person.avatar_url;
        img.alt = '';
        img.onerror = function () {
          avatarEl.textContent = person.initials || '?';
        };
        avatarEl.appendChild(img);
      } else {
        avatarEl.textContent = person.initials || '?';
      }
    }

    const profileLink = document.getElementById('detail-profile-link');
    if (profileLink && person.urls && person.urls.drawer) profileLink.href = person.urls.drawer;

    setDetailStatus(person);
    setDetailToolbar(person);
    setDetailBio(person);
    populateRelatives('detail-parents', [person.father_id, person.mother_id].filter(Boolean));
    populateRelatives('detail-partner', person.partner_id ? [person.partner_id] : []);
    populateRelatives('detail-siblings', person.sibling_ids || []);
    populateRelatives('detail-children', person.child_ids || []);

    overlay.classList.add('is-open');
    panel.classList.add('is-open');

    if (typeof lucide !== 'undefined') {
      lucide.createIcons();
    }
  }

  document.addEventListener('click', (event) => {
    if (!isTouchMode()) return;

    const node = event.target.closest('.person-node[data-person-id]');
    if (!node) {
      if (!event.target.closest('.detail-panel') && !event.target.closest('.detail-overlay')) {
        clearReveal();
      }
      return;
    }

    const person = peopleMap.get(node.dataset.personId);
    if (!person) return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();

    if (revealedId !== person.id || !node.classList.contains('is-touch-revealed')) {
      revealNode(node, person);
      return;
    }

    clearReveal();
    openTouchDetail(person.id);
  }, true);

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') clearReveal();
  });

  window.addEventListener('resize', clearReveal);

  // Keep CSRF helper referenced so minifiers do not treat it as accidental dead code
  // when future touch actions use POST endpoints directly from this module.
  window.ftreeTouchReveal = window.ftreeTouchReveal || { getCsrfToken };
})();
